__all__ = [
    "check_youtube_availability",
    "download_youtube_video",
    "download_youtube_audio",
    "get_youtube_formats",
    "summarize_youtube_video",
    "transcribe_and_summarize_youtube_video",
]

import os
import re
import shutil
import time

import requests
import yt_dlp
from telebot.apihelper import ApiTelegramException

from bot.callback_registry import callback_registry
from bot.keyboards import create_format_selection_markup, create_transcription_confirmation_markup
from bot.texts import READY_FOR_MORE_TEXT
from config import (
    MAX_FILE_SIZE,
    OPENAI_API_KEY,
    TEMP_DIR,
)
from services.openai_client import OpenAITemporaryError
from services.summary_service import (
    SUMMARY_CHUNK_SIZE,
)
from services.summary_service import (
    count_summary_chunks as shared_count_summary_chunks,
)
from services.summary_service import (
    summarize_transcript_text as shared_summarize_transcript_text,
)
from services.transcription_service import (
    OPENAI_TRANSCRIPTION_FILE_LIMIT,
    transcribe_audio_with_openai,
)
from services.transcription_service import (
    split_text_chunks as shared_split_text_chunks,
)
from utils.file_utils import send_with_retry, start_progress_message
from utils.logging_utils import (
    log,
    log_event,
    log_perf,
    measure_time,
    new_operation_id,
    perf_monitor,
)

DEFAULT_VIDEO_SELECTOR = "bv*+ba/b"
DEFAULT_AUDIO_SELECTOR = "bestaudio/best"
FORMAT_SELECTION_UI_LIMIT = 6


def _is_message_not_modified_error(error):
    return "message is not modified" in str(error).lower()


def _create_temp_dir(prefix):
    temp_dir = os.path.join(TEMP_DIR, f"{prefix}_{int(time.time() * 1000)}")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def _cleanup_temp_dir(temp_dir):
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


def _find_downloaded_file(temp_dir, extension=None):
    if not temp_dir or not os.path.isdir(temp_dir):
        return None

    candidates = []
    for name in os.listdir(temp_dir):
        path = os.path.join(temp_dir, name)
        if not os.path.isfile(path) or name.endswith(".part"):
            continue
        if extension and not name.lower().endswith(extension.lower()):
            continue
        candidates.append(path)

    if not candidates:
        return None

    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _resolution_label(height):
    if height >= 2160:
        return f"4K ({height}p)"
    if height >= 1440:
        return f"2K ({height}p)"
    if height >= 1080:
        return "1080p Full HD"
    if height >= 720:
        return "720p HD"
    if height >= 480:
        return "480p SD"
    if height >= 360:
        return "360p"
    if height >= 240:
        return "240p"
    return f"{height}p"


def _extract_requested_height(format_id):
    if not format_id or format_id == "best":
        return None

    match = re.search(r"height<=\??(\d+)", format_id)
    if match:
        return int(match.group(1))
    return None


def _build_video_selector(max_height=None):
    if not max_height:
        return DEFAULT_VIDEO_SELECTOR
    return f"bv*[height<=?{max_height}]+ba/b[height<=?{max_height}]"


def _build_download_candidates(url, requested_format_id):
    if requested_format_id and requested_format_id != "best":
        return [requested_format_id]

    formats_data = _extract_format_options_from_info(_load_youtube_info(url), limit=None)
    candidates = []

    if formats_data and formats_data.get("formats"):
        candidates.extend(fmt["format_id"] for fmt in formats_data["formats"])

    if not candidates:
        candidates.append("best")

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    return unique_candidates


def _split_text_chunks(text, chunk_size=SUMMARY_CHUNK_SIZE):
    return shared_split_text_chunks(text, chunk_size=chunk_size)


def _base_ydl_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }


def _parse_vtt_transcript(vtt_text):
    lines = []
    raw_lines = (vtt_text or "").splitlines()
    previous_text = None

    for index, raw_line in enumerate(raw_lines):
        line = raw_line.strip()
        if not line or line == "WEBVTT":
            continue
        if "-->" in line or line.isdigit():
            continue
        if line.startswith("Kind:") or line.startswith("Language:") or line.startswith("NOTE"):
            continue

        next_line = raw_lines[index + 1].strip() if index + 1 < len(raw_lines) else ""
        if next_line and "-->" in next_line:
            continue

        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line == previous_text:
            continue

        lines.append(line)
        previous_text = line

    return "\n".join(lines)


def _find_any_downloaded_file(temp_dir, extensions):
    for extension in extensions:
        found = _find_downloaded_file(temp_dir, extension=extension)
        if found:
            return found
    return None


def _match_preferred_languages(available_languages, preferred_language):
    matches = []
    for language in sorted(available_languages):
        normalized = (language or "").lower()
        if normalized == preferred_language or normalized.startswith(f"{preferred_language}-"):
            matches.append(language)
    return matches


def _pick_subtitle_language(info):
    manual_languages = set((info.get("subtitles") or {}).keys())
    auto_languages = set((info.get("automatic_captions") or {}).keys())

    for preferred in ("ru", "en"):
        for language in _match_preferred_languages(manual_languages, preferred):
            return language, "subtitles"
        for language in _match_preferred_languages(auto_languages, preferred):
            return language, "automatic_captions"

    if manual_languages:
        return sorted(manual_languages)[0], "subtitles"
    if auto_languages:
        return sorted(auto_languages)[0], "automatic_captions"
    return None, None


def _extract_format_options_from_info(info, *, limit=None):
    if not info:
        return {"title": "YouTube Video", "formats": []}

    title = info.get("title", "YouTube Video")
    heights = {}

    for fmt in info.get("formats", []):
        if fmt.get("vcodec") == "none":
            continue

        height = fmt.get("height")
        if not height:
            continue

        size = fmt.get("filesize") or fmt.get("filesize_approx") or 0
        existing = heights.get(height)
        existing_size = 0
        if existing:
            existing_size = existing.get("filesize") or existing.get("filesize_approx") or 0

        if existing is None or size > existing_size:
            heights[height] = fmt

    formats = []
    sorted_heights = sorted(heights, reverse=True)
    if limit is not None:
        sorted_heights = sorted_heights[:limit]

    for height in sorted_heights:
        fmt = heights[height]
        formats.append(
            {
                "format_id": _build_video_selector(height),
                "format_name": _resolution_label(height),
                "height": height,
                "filesize": fmt.get("filesize", 0),
                "filesize_approx": fmt.get("filesize_approx", 0),
            }
        )

    return {"title": title, "formats": formats}


def _download_youtube_subtitles(url, temp_dir, info=None):
    info = info or {}
    selected_language, source_kind = _pick_subtitle_language(info)
    if not selected_language:
        return {"text": "", "language": None, "source": None}

    output_template = os.path.join(temp_dir, "youtube_subtitles.%(ext)s")
    options = _base_ydl_options()
    options.update(
        {
            "skip_download": True,
            "writesubtitles": source_kind == "subtitles",
            "writeautomaticsub": source_kind == "automatic_captions",
            "subtitleslangs": [selected_language],
            "subtitlesformat": "vtt",
            "outtmpl": output_template,
        }
    )

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)

    transcript_path = _find_downloaded_file(temp_dir, extension=".vtt")
    if not transcript_path:
        return {"text": "", "language": selected_language, "source": source_kind}

    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as subtitle_file:
        return {
            "text": _parse_vtt_transcript(subtitle_file.read()),
            "language": selected_language,
            "source": source_kind,
        }


def _download_youtube_audio_for_summary(url, temp_dir):
    output_template = os.path.join(temp_dir, "youtube_summary_audio.%(ext)s")
    options = _base_ydl_options()
    options.update(
        {
            "format": DEFAULT_AUDIO_SELECTOR,
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "64",
                }
            ],
        }
    )

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    output_path = _find_any_downloaded_file(temp_dir, [".mp3", ".m4a", ".webm", ".mp4"])
    if not output_path:
        raise RuntimeError("Аудиофайл для саммари не создан")

    return info, output_path


def _load_youtube_info(url):
    with yt_dlp.YoutubeDL(_base_ydl_options()) as ydl:
        return ydl.extract_info(url, download=False) or {}


def _build_subtitle_failure_message(error=None):
    if error and "429" in str(error):
        return (
            "⚠️ YouTube сейчас не отдал субтитры из-за ограничения запросов. "
            "Могу запустить платную расшифровку аудио через OpenAI."
        )
    return "⚠️ Не удалось получить субтитры для этого видео. Могу запустить платную расшифровку аудио через OpenAI."


def _offer_transcription_fallback(bot, chat_id, url, message):
    url_id = callback_registry.register_action_url(url)
    bot.send_message(
        chat_id,
        message,
        reply_markup=create_transcription_confirmation_markup(url_id),
    )


def _build_selection_formats(url, formats):
    selection_formats = []
    for format_info in formats:
        selection_id = callback_registry.register_format_selection(url, format_info["format_id"])
        selection_formats.append(
            {
                **format_info,
                "callback_data": f"f:{selection_id}",
            }
        )
    return selection_formats


def _show_format_selection_prompt(bot, chat_id, url, *, message_id=None, prompt_text=None, max_height=None):
    formats_data = get_youtube_formats(url)
    available_formats = formats_data.get("formats") or []

    if max_height is not None:
        lowered_formats = [
            format_info
            for format_info in available_formats
            if (format_info.get("height") or 0) < max_height
        ]
        if lowered_formats:
            available_formats = lowered_formats

    if not available_formats:
        return False

    markup = create_format_selection_markup(
        _build_selection_formats(url, available_formats),
        best_callback_data=(
            None
            if max_height is not None
            else f"f:{callback_registry.register_format_selection(url, 'best')}"
        ),
    )
    prompt = prompt_text or f"📹 Выберите качество видео для:\n{formats_data.get('title', 'YouTube Video')}"

    if message_id:
        try:
            bot.edit_message_text(
                prompt,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
            )
            return True
        except Exception as e:
            log(f"Ошибка при обновлении сообщения с выбором качества: {e}", level="WARNING")

    bot.send_message(chat_id, prompt, reply_markup=markup)
    return True


def _summarize_transcript_text(transcript_text, title=None, transcript_source=None, transcript_language=None):
    return shared_summarize_transcript_text(
        transcript_text,
        title=title,
        transcript_source=transcript_source,
        transcript_language=transcript_language,
    )


def _count_summary_chunks(transcript_text):
    return shared_count_summary_chunks(transcript_text)


def _send_summary_result(
    bot,
    chat_id,
    summary,
    title,
    status_message_id,
    success_text="✅ Саммари готово.",
):
    _finalize_status_message(bot, chat_id, status_message_id, success_text)
    bot.send_message(chat_id, f"🧠 Саммари для: {title}\n\n{summary}")
    bot.send_message(chat_id, READY_FOR_MORE_TEXT)


def _ensure_status_message(bot, chat_id, message_id, text):
    if message_id:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
            return message_id
        except ApiTelegramException as e:
            if _is_message_not_modified_error(e):
                return message_id
            log(f"Ошибка при обновлении сообщения: {e}", level="WARNING")
        except Exception as e:
            log(f"Ошибка при обновлении сообщения: {e}", level="WARNING")

    message = bot.send_message(chat_id, text)
    return message.message_id


def _finalize_status_message(bot, chat_id, message_id, text):
    if not message_id:
        return

    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
    except ApiTelegramException as e:
        if _is_message_not_modified_error(e):
            return
        log(f"Не удалось финализировать статусное сообщение: {e}", level="DEBUG")
    except Exception as e:
        log(f"Не удалось финализировать статусное сообщение: {e}", level="DEBUG")


@perf_monitor
def check_youtube_availability(url):
    """Проверка доступности видео на YouTube через yt-dlp."""
    log(f"Проверка доступности YouTube: {url}")
    try:
        with measure_time("CHECK|youtube_extract_info"):
            with yt_dlp.YoutubeDL(_base_ydl_options()) as ydl:
                info = ydl.extract_info(url, download=False)
        available = bool(info)
        log(f"YouTube контент {'доступен' if available else 'недоступен'}")
        return available
    except Exception as e:
        log(f"Ошибка при проверке YouTube: {e}", level="WARNING")
        return False


@perf_monitor
def get_youtube_formats(url):
    """Получение доступных форматов видео с YouTube."""
    try:
        with measure_time("INFO|youtube_get_formats"):
            info = _load_youtube_info(url)

        return _extract_format_options_from_info(info, limit=FORMAT_SELECTION_UI_LIMIT)
    except Exception as e:
        log(f"Ошибка при получении форматов YouTube: {e}", level="ERROR")
        return {"title": "YouTube Video", "formats": []}


@perf_monitor
def download_youtube_video(bot, chat_id, url, message_id=None, format_id=None):
    """Скачивание видео с YouTube."""
    op_id = new_operation_id("yt-video")
    if not format_id:
        if _show_format_selection_prompt(bot, chat_id, url, message_id=message_id):
            return

        format_id = "best"

    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Начинаю скачивание видео...")
    progress_stop = start_progress_message(bot, chat_id, "Скачивание видео с YouTube", status_message_id)
    log_event("youtube_video_started", op=op_id, chat_id=chat_id, url=url, requested_format=format_id or "best")

    try:
        requested_format = format_id or "best"
        candidate_formats = _build_download_candidates(url, requested_format)
        info = None
        output_path = None
        file_size_mb = 0
        temp_dir = None
        last_error = None

        for attempt_index, candidate_format in enumerate(candidate_formats, start=1):
            attempt_temp_dir = _create_temp_dir("youtube_video")
            try:
                requested_height = _extract_requested_height(candidate_format)
                selector = _build_video_selector(requested_height)
                output_template = os.path.join(attempt_temp_dir, "youtube_video.%(ext)s")
                options = _base_ydl_options()
                options.update(
                    {
                        "format": selector,
                        "merge_output_format": "mp4",
                        "outtmpl": output_template,
                    }
                )

                log_event(
                    "youtube_video_attempt_started",
                    op=op_id,
                    chat_id=chat_id,
                    attempt=attempt_index,
                    candidate_format=candidate_format,
                )
                with measure_time("DOWNLOAD|youtube_video_download"):
                    with yt_dlp.YoutubeDL(options) as ydl:
                        attempt_info = ydl.extract_info(url, download=True)

                attempt_output_path = _find_downloaded_file(attempt_temp_dir)
                if not attempt_output_path:
                    raise RuntimeError("Не удалось скачать видео через yt-dlp")

                attempt_file_size = os.path.getsize(attempt_output_path)
                attempt_file_size_mb = attempt_file_size / (1024 * 1024)
                log_perf(f"FILE_SIZE|youtube_video|{attempt_file_size_mb:.2f}MB")

                if attempt_file_size > MAX_FILE_SIZE:
                    log_event(
                        "youtube_video_attempt_rejected_large",
                        op=op_id,
                        chat_id=chat_id,
                        attempt=attempt_index,
                        candidate_format=candidate_format,
                        size_mb=f"{attempt_file_size_mb:.2f}",
                    )
                    _cleanup_temp_dir(attempt_temp_dir)

                    if requested_format == "best" and attempt_index < len(candidate_formats):
                        log(
                            f"Файл {attempt_file_size_mb:.2f}MB слишком большой для Telegram, пробую качество ниже",
                        )
                        continue

                    if requested_format != "best":
                        requested_height = _extract_requested_height(candidate_format)
                        if _show_format_selection_prompt(
                            bot,
                            chat_id,
                            url,
                            message_id=status_message_id,
                            prompt_text=(
                                "⚠️ Выбранное качество слишком большое для Telegram. "
                                "Выберите вариант ниже:"
                            ),
                            max_height=requested_height,
                        ):
                            log_event(
                                "youtube_video_reoffer_lower_quality",
                                op=op_id,
                                chat_id=chat_id,
                                requested_format=candidate_format,
                                size_mb=f"{attempt_file_size_mb:.2f}",
                            )
                            return

                    _finalize_status_message(
                        bot,
                        chat_id,
                        status_message_id,
                        "⚠️ Видео оказалось слишком большим для Telegram.",
                    )
                    log_event(
                        "youtube_video_rejected_large",
                        op=op_id,
                        chat_id=chat_id,
                        size_mb=f"{attempt_file_size_mb:.2f}",
                    )
                    bot.send_message(
                        chat_id,
                        f"⚠️ Видео слишком большое для отправки в Telegram ({attempt_file_size_mb:.2f} МБ > 50 МБ)",
                    )
                    return

                info = attempt_info
                output_path = attempt_output_path
                file_size_mb = attempt_file_size_mb
                temp_dir = attempt_temp_dir
                format_id = candidate_format
                break
            except Exception as e:
                last_error = e
                _cleanup_temp_dir(attempt_temp_dir)
                log_event(
                    "youtube_video_attempt_failed",
                    level="WARNING",
                    op=op_id,
                    chat_id=chat_id,
                    attempt=attempt_index,
                    candidate_format=candidate_format,
                    error=e,
                )
                if requested_format == "best" and attempt_index < len(candidate_formats):
                    continue
                raise

        if not output_path:
            if last_error:
                raise last_error
            raise RuntimeError("Не удалось скачать видео через yt-dlp")

        title = "✅ Ваше видео с YouTube"
        if info and info.get("title"):
            title = f"✅ {info['title']}"

        with measure_time("UPLOAD|youtube_video_upload"):
            with open(output_path, "rb") as video_file:
                sent_message = send_with_retry(bot.send_video, chat_id, video_file, caption=title)

        if sent_message is None:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось отправить видео в Telegram.")
            log_event("youtube_video_upload_failed", level="ERROR", op=op_id, chat_id=chat_id)
            bot.send_message(chat_id, "❌ Не удалось отправить видео в Telegram.")
            return

        _finalize_status_message(
            bot,
            chat_id,
            status_message_id,
            "✅ Видео с YouTube успешно отправлено.",
        )
        log_event(
            "youtube_video_finished",
            op=op_id,
            chat_id=chat_id,
            size_mb=f"{file_size_mb:.2f}",
            actual_format=format_id,
        )
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except Exception as e:
        log_event("youtube_video_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось скачать видео с YouTube.")
        bot.send_message(chat_id, "❌ Не удалось скачать видео. Попробуйте другую ссылку.")
    finally:
        progress_stop.set()
        if "temp_dir" in locals():
            _cleanup_temp_dir(temp_dir)


@perf_monitor
def download_youtube_audio(bot, chat_id, url, message_id=None, failure_message_text=None):
    """Извлечение аудио из видео на YouTube."""
    op_id = new_operation_id("yt-audio")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Извлекаю аудио...")
    progress_stop = start_progress_message(bot, chat_id, "Извлечение аудио", status_message_id)
    temp_dir = _create_temp_dir("youtube_audio")
    log_event("youtube_audio_started", op=op_id, chat_id=chat_id, url=url)

    try:
        output_template = os.path.join(temp_dir, "youtube_audio.%(ext)s")
        options = _base_ydl_options()
        options.update(
            {
                "format": DEFAULT_AUDIO_SELECTOR,
                "outtmpl": output_template,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )

        with measure_time("DOWNLOAD|youtube_audio_download"):
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)

        output_path = _find_downloaded_file(temp_dir, extension=".mp3")
        if not output_path:
            raise RuntimeError("MP3 файл не создан")

        file_size = os.path.getsize(output_path)
        file_size_mb = file_size / (1024 * 1024)
        log_perf(f"FILE_SIZE|youtube_audio|{file_size_mb:.2f}MB")

        if file_size > MAX_FILE_SIZE:
            _finalize_status_message(bot, chat_id, status_message_id, "⚠️ Аудио оказалось слишком большим для Telegram.")
            log_event("youtube_audio_rejected_large", op=op_id, chat_id=chat_id, size_mb=f"{file_size_mb:.2f}")
            bot.send_message(chat_id, "⚠️ Аудио слишком большое для отправки в Telegram (>50MB)")
            return

        title = info.get("track") or info.get("title") or "YouTube Audio"
        performer = info.get("artist") or info.get("uploader") or "Unknown Artist"

        with measure_time("UPLOAD|youtube_audio_upload"):
            with open(output_path, "rb") as audio_file:
                sent_message = send_with_retry(
                    bot.send_audio,
                    chat_id,
                    audio_file,
                    title=title,
                    performer=performer,
                    caption="✅ Ваше аудио из YouTube",
                )

        if sent_message is None:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось отправить аудио в Telegram.")
            log_event("youtube_audio_upload_failed", level="ERROR", op=op_id, chat_id=chat_id)
            bot.send_message(chat_id, "❌ Не удалось отправить аудио в Telegram.")
            return

        _finalize_status_message(bot, chat_id, status_message_id, "✅ Аудио из YouTube успешно отправлено.")
        log_event("youtube_audio_finished", op=op_id, chat_id=chat_id, size_mb=f"{file_size_mb:.2f}")
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except Exception as e:
        log_event("youtube_audio_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось извлечь аудио из YouTube.")
        bot.send_message(
            chat_id,
            failure_message_text or "❌ Не удалось извлечь аудио. Попробуйте другую ссылку.",
        )
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)


@perf_monitor
def summarize_youtube_video(bot, chat_id, url, message_id=None):
    """Суммаризация YouTube-видео только через субтитры с предложением платного fallback."""
    op_id = new_operation_id("yt-summary")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Готовлю саммари видео...")
    progress_stop = start_progress_message(bot, chat_id, "Подготовка саммари YouTube", status_message_id)
    temp_dir = _create_temp_dir("youtube_summary")
    log_event("youtube_summary_started", op=op_id, chat_id=chat_id, url=url)

    try:
        if not OPENAI_API_KEY:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не настроен OpenAI API key.")
            bot.send_message(
                chat_id,
                "❌ Для саммари нужен `OPENAI_API_KEY` в конфиге бота.",
                parse_mode="Markdown",
            )
            return

        title = "YouTube Video"
        transcript_text = ""
        transcript_source = None
        transcript_language = None

        try:
            with measure_time("INFO|youtube_summary_load_info"):
                info = _load_youtube_info(url)
            title = info.get("title") or title

            _ensure_status_message(bot, chat_id, status_message_id, "⏳ Пробую получить субтитры видео...")
            selected_language, selected_source = _pick_subtitle_language(info)
            if not selected_language:
                log_event(
                    "youtube_summary_subtitles_unavailable",
                    op=op_id,
                    chat_id=chat_id,
                    reason="no_subtitles_in_info",
                )
                _finalize_status_message(bot, chat_id, status_message_id, "⚠️ Субтитры недоступны.")
                _offer_transcription_fallback(
                    bot,
                    chat_id,
                    url,
                    "⚠️ У этого видео не нашлись доступные субтитры. "
                    "Запустить платную расшифровку аудио и затем сделать саммари?",
                )
                return

            log_event(
                "youtube_summary_subtitles_selected",
                op=op_id,
                chat_id=chat_id,
                language=selected_language,
                source=selected_source,
            )
            with measure_time("DOWNLOAD|youtube_summary_subtitles"):
                subtitles_result = _download_youtube_subtitles(url, temp_dir, info=info)
            transcript_text = subtitles_result.get("text") or ""
            transcript_source = subtitles_result.get("source")
            transcript_language = subtitles_result.get("language")
        except Exception as e:
            log_event("youtube_summary_subtitles_failed", level="WARNING", op=op_id, chat_id=chat_id, error=e)
            _finalize_status_message(bot, chat_id, status_message_id, "⚠️ Не удалось получить субтитры.")
            _offer_transcription_fallback(bot, chat_id, url, _build_subtitle_failure_message(error=e))
            return

        if not transcript_text:
            log_event(
                "youtube_summary_subtitles_unavailable",
                op=op_id,
                chat_id=chat_id,
                reason="empty_transcript",
            )
            _finalize_status_message(bot, chat_id, status_message_id, "⚠️ Субтитры пустые или недоступны.")
            _offer_transcription_fallback(
                bot,
                chat_id,
                url,
                "⚠️ YouTube не отдал пригодный текст субтитров. "
                "Запустить платную расшифровку аудио и затем сделать саммари?",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Собираю саммари...")
        chunk_count = _count_summary_chunks(transcript_text)
        log_event(
            "youtube_summary_chunking",
            op=op_id,
            chat_id=chat_id,
            transcript_source=transcript_source,
            chunks=chunk_count,
        )
        with measure_time("OPENAI|youtube_summary_response"):
            summary = _summarize_transcript_text(
                transcript_text,
                title=title,
                transcript_source=transcript_source,
                transcript_language=transcript_language,
            )
        if not summary:
            raise RuntimeError("OpenAI вернул пустое саммари")

        _send_summary_result(bot, chat_id, summary, title, status_message_id)
        log_event("youtube_summary_finished", op=op_id, chat_id=chat_id)
    except OpenAITemporaryError as e:
        log_event("youtube_summary_openai_unavailable", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ OpenAI временно недоступен.")
        bot.send_message(
            chat_id, "❌ Не удалось связаться с OpenAI при построении саммари. Попробуйте ещё раз чуть позже."
        )
    except requests.HTTPError as e:
        log_event("youtube_summary_openai_http_error", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить саммари.")
        bot.send_message(chat_id, "❌ OpenAI API вернул ошибку при построении саммари.")
    except Exception as e:
        log_event("youtube_summary_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить саммари.")
        bot.send_message(chat_id, "❌ Не удалось подготовить саммари для этого видео.")
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)


@perf_monitor
def transcribe_and_summarize_youtube_video(bot, chat_id, url, message_id=None):
    """Платная расшифровка аудио YouTube и последующая суммаризация."""
    op_id = new_operation_id("yt-summary-stt")
    status_message_id = _ensure_status_message(
        bot,
        chat_id,
        message_id,
        "⏳ Запускаю расшифровку аудио и саммари...",
    )
    progress_stop = start_progress_message(bot, chat_id, "Платная расшифровка и саммари YouTube", status_message_id)
    temp_dir = _create_temp_dir("youtube_summary_transcribe")
    log_event("youtube_summary_transcription_started", op=op_id, chat_id=chat_id, url=url)

    try:
        if not OPENAI_API_KEY:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не настроен OpenAI API key.")
            bot.send_message(
                chat_id,
                "❌ Для расшифровки и саммари нужен `OPENAI_API_KEY` в конфиге бота.",
                parse_mode="Markdown",
            )
            return

        title = "YouTube Video"
        transcript_language = None

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Скачиваю аудио для расшифровки...")
        with measure_time("DOWNLOAD|youtube_summary_audio_download"):
            info, audio_path = _download_youtube_audio_for_summary(url, temp_dir)
        title = info.get("title") or title
        transcript_language = info.get("language") or transcript_language

        audio_size = os.path.getsize(audio_path)
        audio_size_mb = audio_size / (1024 * 1024)
        log_event(
            "youtube_summary_audio_ready",
            op=op_id,
            chat_id=chat_id,
            size_mb=f"{audio_size_mb:.2f}",
        )
        if audio_size > OPENAI_TRANSCRIPTION_FILE_LIMIT:
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "⚠️ Видео слишком длинное для автоматического саммари.",
            )
            bot.send_message(
                chat_id,
                "⚠️ Аудио оказалось слишком большим для транскрипции через OpenAI "
                f"({audio_size_mb:.2f} МБ > 25 МБ). "
                "Попробуйте более короткое видео.",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Распознаю речь через OpenAI...")
        with measure_time("OPENAI|youtube_audio_transcription"):
            transcript_text = transcribe_audio_with_openai(audio_path)

        if not transcript_text:
            raise RuntimeError("Не удалось получить текст из транскрипции")

        chunk_count = _count_summary_chunks(transcript_text)
        log_event(
            "youtube_summary_chunking",
            op=op_id,
            chat_id=chat_id,
            transcript_source="openai_transcription",
            chunks=chunk_count,
        )

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Собираю саммари...")
        with measure_time("OPENAI|youtube_summary_response"):
            summary = _summarize_transcript_text(
                transcript_text,
                title=title,
                transcript_source="openai_transcription",
                transcript_language=transcript_language,
            )
        if not summary:
            raise RuntimeError("OpenAI вернул пустое саммари")

        _send_summary_result(
            bot,
            chat_id,
            summary,
            title,
            status_message_id,
            success_text="✅ Расшифровка и саммари готовы.",
        )
        log_event("youtube_summary_transcription_finished", op=op_id, chat_id=chat_id)
    except OpenAITemporaryError as e:
        log_event("youtube_summary_transcription_openai_unavailable", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ OpenAI временно недоступен.")
        bot.send_message(
            chat_id,
            "❌ Не удалось связаться с OpenAI при расшифровке или подготовке саммари. Попробуйте ещё раз чуть позже.",
        )
    except requests.HTTPError as e:
        log_event("youtube_summary_transcription_http_error", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить расшифровку или саммари.")
        bot.send_message(chat_id, "❌ OpenAI API вернул ошибку при расшифровке или суммаризации.")
    except Exception as e:
        log_event("youtube_summary_transcription_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить расшифровку или саммари.")
        bot.send_message(chat_id, "❌ Не удалось подготовить расшифровку и саммари для этого видео.")
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)
