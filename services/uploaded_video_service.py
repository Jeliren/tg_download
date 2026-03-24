"""Сценарии расшифровки и саммари для загруженных пользователем видео."""

__all__ = [
    "summarize_uploaded_video",
    "transcribe_uploaded_video",
]

import os
import subprocess

import requests

from bot.texts import READY_FOR_MORE_TEXT
from config import OPENAI_API_KEY
from services.converter_service import check_ffmpeg
from services.openai_client import OpenAITemporaryError
from services.summary_service import count_summary_chunks, summarize_transcript_text
from services.transcription_service import (
    OPENAI_TRANSCRIPTION_FILE_LIMIT,
    send_text_chunks,
    split_text_chunks,
    transcribe_audio_with_openai,
)
from services.uploaded_media_service import (
    UploadedMediaNoAudioError,
)
from services.uploaded_media_service import (
    cleanup_temp_dir as _cleanup_temp_dir,
)
from services.uploaded_media_service import (
    create_temp_dir as _create_temp_dir,
)
from services.uploaded_media_service import (
    ensure_status_message as _ensure_status_message,
)
from services.uploaded_media_service import (
    finalize_status_message as _finalize_status_message,
)
from services.uploaded_media_service import (
    prepare_uploaded_video_audio as _prepare_uploaded_video_audio,
)
from utils.file_utils import start_progress_message
from utils.logging_utils import log_event, measure_time, new_operation_id, perf_monitor


def _send_summary_result(bot, chat_id, summary, status_message_id):
    _finalize_status_message(bot, chat_id, status_message_id, "✅ Саммари готово.")
    bot.send_message(chat_id, f"🧠 Саммари загруженного видео\n\n{summary}")
    bot.send_message(chat_id, READY_FOR_MORE_TEXT)


@perf_monitor
def transcribe_uploaded_video(bot, chat_id, user_id, video_file_id, message_id=None):
    """Извлекает аудио из загруженного видео, расшифровывает его и отправляет пользователю."""
    op_id = new_operation_id("tg-video-transcript")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Запускаю расшифровку видео...")
    progress_stop = start_progress_message(bot, chat_id, "Расшифровка загруженного видео", status_message_id)
    temp_dir = _create_temp_dir("uploaded_video_transcription")
    log_event("uploaded_video_transcription_started", op=op_id, chat_id=chat_id, user_id=user_id)

    try:
        if not OPENAI_API_KEY:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не настроен OpenAI API key.")
            bot.send_message(
                chat_id,
                "❌ Для расшифровки нужен `OPENAI_API_KEY` в конфиге бота.",
                parse_mode="Markdown",
            )
            return

        if not check_ffmpeg():
            _finalize_status_message(bot, chat_id, status_message_id, "❌ ffmpeg недоступен.")
            bot.send_message(chat_id, "❌ Для обработки загруженного видео нужен ffmpeg.")
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Скачиваю видео из Telegram...")
        with measure_time("DOWNLOAD|uploaded_video"):
            audio_path = _prepare_uploaded_video_audio(bot, video_file_id, temp_dir)

        audio_size = os.path.getsize(audio_path)
        audio_size_mb = audio_size / (1024 * 1024)
        log_event(
            "uploaded_video_transcription_audio_ready",
            op=op_id,
            chat_id=chat_id,
            size_mb=f"{audio_size_mb:.2f}",
        )
        if audio_size > OPENAI_TRANSCRIPTION_FILE_LIMIT:
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "⚠️ Видео слишком длинное для автоматической расшифровки.",
            )
            bot.send_message(
                chat_id,
                "⚠️ Аудио оказалось слишком большим для транскрипции через OpenAI "
                f"({audio_size_mb:.2f} МБ > 25 МБ). "
                "Попробуйте более короткое видео.",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Распознаю речь через OpenAI...")
        with measure_time("OPENAI|uploaded_video_transcription"):
            transcript_text = transcribe_audio_with_openai(audio_path)

        if not transcript_text:
            raise RuntimeError("Не удалось получить текст из транскрипции загруженного видео")

        transcript_chunks = split_text_chunks(transcript_text)
        log_event(
            "uploaded_video_transcription_chunking",
            op=op_id,
            chat_id=chat_id,
            chunks=len(transcript_chunks),
        )
        send_text_chunks(bot, chat_id, transcript_text)
        _finalize_status_message(bot, chat_id, status_message_id, "✅ Расшифровка видео готова.")
        log_event("uploaded_video_transcription_finished", op=op_id, chat_id=chat_id, user_id=user_id)
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except UploadedMediaNoAudioError:
        _finalize_status_message(bot, chat_id, status_message_id, "⚠️ В видео нет аудио.")
        bot.send_message(chat_id, "⚠️ В этом видео нет аудиодорожки, поэтому расшифровка недоступна.")
    except OpenAITemporaryError as e:
        log_event("uploaded_video_transcription_openai_unavailable", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ OpenAI временно недоступен.")
        bot.send_message(
            chat_id, "❌ Не удалось связаться с OpenAI при расшифровке видео. Попробуйте ещё раз чуть позже."
        )
    except requests.HTTPError as e:
        log_event("uploaded_video_transcription_http_error", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить расшифровку.")
        bot.send_message(chat_id, "❌ OpenAI API вернул ошибку при расшифровке видео.")
    except subprocess.TimeoutExpired:
        log_event("uploaded_video_transcription_timeout", level="ERROR", op=op_id, chat_id=chat_id)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Истекло время обработки видео.")
        bot.send_message(chat_id, "❌ Видео обрабатывалось слишком долго. Попробуйте файл покороче.")
    except Exception as e:
        log_event("uploaded_video_transcription_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось расшифровать видео.")
        bot.send_message(chat_id, "❌ Не удалось подготовить расшифровку для этого видео.")
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)


@perf_monitor
def summarize_uploaded_video(bot, chat_id, user_id, video_file_id, message_id=None):
    """Извлекает аудио из загруженного видео, делает транскрипт и строит саммари."""
    op_id = new_operation_id("tg-video-summary")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Готовлю саммари видео...")
    progress_stop = start_progress_message(bot, chat_id, "Саммари загруженного видео", status_message_id)
    temp_dir = _create_temp_dir("uploaded_video_summary")
    log_event("uploaded_video_summary_started", op=op_id, chat_id=chat_id, user_id=user_id)

    try:
        if not OPENAI_API_KEY:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не настроен OpenAI API key.")
            bot.send_message(
                chat_id,
                "❌ Для саммари нужен `OPENAI_API_KEY` в конфиге бота.",
                parse_mode="Markdown",
            )
            return

        if not check_ffmpeg():
            _finalize_status_message(bot, chat_id, status_message_id, "❌ ffmpeg недоступен.")
            bot.send_message(chat_id, "❌ Для обработки загруженного видео нужен ffmpeg.")
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Скачиваю видео из Telegram...")
        with measure_time("DOWNLOAD|uploaded_video"):
            audio_path = _prepare_uploaded_video_audio(bot, video_file_id, temp_dir)

        audio_size = os.path.getsize(audio_path)
        audio_size_mb = audio_size / (1024 * 1024)
        log_event(
            "uploaded_video_summary_audio_ready",
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
        with measure_time("OPENAI|uploaded_video_transcription"):
            transcript_text = transcribe_audio_with_openai(audio_path)

        if not transcript_text:
            raise RuntimeError("Не удалось получить текст из транскрипции загруженного видео")

        chunk_count = count_summary_chunks(transcript_text)
        log_event(
            "uploaded_video_summary_chunking",
            op=op_id,
            chat_id=chat_id,
            transcript_source="openai_transcription",
            chunks=chunk_count,
        )

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Собираю саммари...")
        with measure_time("OPENAI|uploaded_video_summary"):
            summary = summarize_transcript_text(
                transcript_text,
                title="Загруженное видео",
                transcript_source="openai_transcription",
                transcript_language=None,
            )

        if not summary:
            raise RuntimeError("OpenAI вернул пустое саммари")

        _send_summary_result(bot, chat_id, summary, status_message_id)
        log_event("uploaded_video_summary_finished", op=op_id, chat_id=chat_id, user_id=user_id)
    except UploadedMediaNoAudioError:
        _finalize_status_message(bot, chat_id, status_message_id, "⚠️ В видео нет аудио.")
        bot.send_message(chat_id, "⚠️ В этом видео нет аудиодорожки, поэтому саммари недоступно.")
    except OpenAITemporaryError as e:
        log_event("uploaded_video_summary_openai_unavailable", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ OpenAI временно недоступен.")
        bot.send_message(
            chat_id, "❌ Не удалось связаться с OpenAI при подготовке саммари. Попробуйте ещё раз чуть позже."
        )
    except requests.HTTPError as e:
        log_event("uploaded_video_summary_http_error", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить саммари.")
        bot.send_message(chat_id, "❌ OpenAI API вернул ошибку при построении саммари.")
    except subprocess.TimeoutExpired:
        log_event("uploaded_video_summary_timeout", level="ERROR", op=op_id, chat_id=chat_id)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Истекло время обработки видео.")
        bot.send_message(chat_id, "❌ Видео обрабатывалось слишком долго. Попробуйте файл покороче.")
    except Exception as e:
        log_event("uploaded_video_summary_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить саммари.")
        bot.send_message(chat_id, "❌ Не удалось подготовить саммари для этого видео.")
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)
