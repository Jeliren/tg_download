__all__ = [
    "check_instagram_availability",
    "download_instagram_video",
    "download_instagram_audio",
    "download_instagram_description",
    "transcribe_instagram_reel",
]

import html
import json
import os
import random
import re
import shutil
import subprocess
import time
from urllib.parse import urlparse, urlunparse

import requests
import yt_dlp
from requests.adapters import HTTPAdapter
from telebot import types
from telebot.apihelper import ApiTelegramException

from bot.texts import READY_FOR_MORE_TEXT
from config import (
    EXTERNAL_CONNECT_TIMEOUT,
    EXTERNAL_READ_TIMEOUT,
    INSTAGRAM_COOKIES_FILE,
    MAX_DOWNLOAD_ATTEMPTS,
    MAX_FILE_SIZE,
    OPENAI_API_KEY,
    RETRY_DELAY,
    TEMP_DIR,
)
from services.instagram_account_service import (
    InstagramAccountError,
    download_video_via_account,
    get_media_via_account,
    instagram_account_is_configured,
    instagram_account_supports_url,
)
from services.openai_client import OpenAITemporaryError
from services.platforms import is_instagram_url
from services.transcription_service import (
    OPENAI_TRANSCRIPTION_FILE_LIMIT,
    send_text_chunks,
    split_text_chunks,
    transcribe_audio_with_openai,
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

TIMEOUT = (EXTERNAL_CONNECT_TIMEOUT, EXTERNAL_READ_TIMEOUT)
MAX_RETRIES = 3
TELEGRAM_TEXT_LIMIT = 4096
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
]
HTML_MEDIA_PATTERNS = [
    r'"video_url":"([^"]+)"',
    r'"video_versions":\[{"type":\d+,"width":\d+,"height":\d+,"url":"([^"]+)"',
    r'"contentUrl":"([^"]+\.mp4[^"]*)"',
    r'<meta property="og:video" content="([^"]+)"',
    r'<meta property="og:video:secure_url" content="([^"]+)"',
    r'<video[^>]*src="([^"]+)"',
    r'<source src="([^"]+)"',
    r'"playable_url":"([^"]+)"',
]
HTML_DESCRIPTION_PATTERNS = [
    r'<meta property="og:description" content="([^"]+)"',
    r'<meta name="description" content="([^"]+)"',
    r'<meta name="twitter:description" content="([^"]+)"',
]
TELEGRAM_SAFE_VIDEO_CODECS = {"h264"}
TELEGRAM_SAFE_AUDIO_CODECS = {"aac", "mp3", None}
INSTAGRAM_AUTH_REQUIRED_MARKERS = (
    "login required",
    "cookies-from-browser",
    "use --cookies",
    "authentication",
)
INSTAGRAM_RATE_LIMIT_MARKERS = (
    "rate-limit reached",
    "too many requests",
    "please wait a few minutes",
)
INSTAGRAM_AUDIENCE_RESTRICTED_MARKERS = (
    "unavailable for certain audiences",
    "this content may be inappropriate",
)
INSTAGRAM_NOT_FOUND_MARKERS = (
    "404",
    "not found",
    "page is not available",
    "the reel may have been removed",
)
INSTAGRAM_NETWORK_ERROR_MARKERS = (
    "timed out",
    "connection aborted",
    "connection reset",
    "temporarily unavailable",
    "name or service not known",
    "temporary failure in name resolution",
    "network is unreachable",
)
INSTAGRAM_ACCOUNT_REASON_MAP = {
    "bad_credentials": "account_auth_failed",
    "challenge_required": "account_challenge_required",
    "two_factor_required": "account_two_factor_required",
    "login_required": "auth_required",
    "rate_limited": "rate_limited",
    "video_missing": "unknown",
    "not_configured": "not_configured",
    "unsupported_url": "unsupported_url",
}


class InstagramUnavailableError(RuntimeError):
    def __init__(self, reason, detail=None):
        self.reason = reason or "unknown"
        self.detail = str(detail or "").strip()
        super().__init__(self.detail or self.reason)


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


def _random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _create_session():
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=MAX_RETRIES)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(_random_headers())
    return session


def _iter_yt_dlp_auth_options():
    yield "no-auth", {}

    if INSTAGRAM_COOKIES_FILE and os.path.exists(INSTAGRAM_COOKIES_FILE):
        yield f"cookiefile:{INSTAGRAM_COOKIES_FILE}", {"cookiefile": INSTAGRAM_COOKIES_FILE}
    elif INSTAGRAM_COOKIES_FILE:
        log(
            f"Optional Instagram cookiefile не найден: {INSTAGRAM_COOKIES_FILE}. Продолжаю в public mode.",
            level="WARNING",
        )


def _build_yt_dlp_options(format_type, temp_dir=None, download=True, auth_options=None):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": EXTERNAL_CONNECT_TIMEOUT + EXTERNAL_READ_TIMEOUT,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "http_headers": _random_headers(),
    }
    if download and temp_dir:
        options["outtmpl"] = os.path.join(temp_dir, f"instagram_{format_type}.%(ext)s")

    if format_type == "audio":
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
        )
    else:
        # Telegram заметно стабильнее переваривает обычный MP4/H.264, чем произвольный bestvideo.
        options.update(
            {
                "format": (
                    "bestvideo[ext=mp4][vcodec*=avc1]+bestaudio[ext=m4a]/"
                    "best[ext=mp4][vcodec*=avc1]/best[ext=mp4]/bv*+ba/b"
                ),
                "merge_output_format": "mp4",
            }
        )

    if auth_options:
        options.update(auth_options)

    return options


def _classify_instagram_error(error):
    text = str(error).lower()
    if any(marker in text for marker in INSTAGRAM_AUDIENCE_RESTRICTED_MARKERS):
        return "audience_restricted"
    if any(marker in text for marker in INSTAGRAM_RATE_LIMIT_MARKERS):
        return "rate_limited"
    if any(marker in text for marker in INSTAGRAM_AUTH_REQUIRED_MARKERS):
        return "auth_required"
    if any(marker in text for marker in INSTAGRAM_NOT_FOUND_MARKERS):
        return "not_found"
    if any(marker in text for marker in INSTAGRAM_NETWORK_ERROR_MARKERS):
        return "network"
    return "unknown"


def _is_retryable_instagram_error(reason):
    return reason in {"network", "unknown"}


def _backoff_seconds(attempt):
    return max(1, RETRY_DELAY) * (2 ** max(0, attempt - 1))


def _sleep_before_retry(label, attempt):
    delay = _backoff_seconds(attempt)
    log(f"{label}: жду {delay} сек. перед повторной попыткой", level="INFO")
    time.sleep(delay)


def _build_instagram_user_message(reason, action="скачать этот рилс"):
    messages = {
        "account_auth_failed": ("Instagram service account не смог авторизоваться. Проверьте логин и пароль сервиса."),
        "account_challenge_required": (
            "Instagram запросил challenge для service account. "
            "Пока challenge не будет пройден, получить этот рилс стабильно не получится."
        ),
        "account_two_factor_required": (
            "Instagram требует 2FA-код для service account. Автоматическая выдача этого рилса сейчас недоступна."
        ),
        "auth_required": (
            "Instagram не отдал этот рилс в публичном режиме без авторизации. "
            "Такое бывает из-за login required или анти-бот ограничений."
        ),
        "rate_limited": ("Instagram временно ограничил доступ к этому рилсу. Попробуйте повторить запрос чуть позже."),
        "audience_restricted": (
            "Этот рилс ограничен по аудитории или помечен как недоступный для части пользователей. "
            f"Поэтому бот не может {action}."
        ),
        "not_found": ("Рилс не найден или уже недоступен по этой ссылке."),
        "network": ("Не удалось стабильно связаться с Instagram. Попробуйте ещё раз чуть позже."),
        "unsupported_url": (
            "Эта Instagram-ссылка не поддерживается server-side account mode и не была доступна через public fallback."
        ),
        "unknown": (
            "Instagram не отдал данные в публичном режиме. "
            "Бот работает в best-effort режиме, поэтому часть рилсов может быть временно недоступна."
        ),
    }
    return messages.get(reason, messages["unknown"])


def _map_account_reason(reason):
    return INSTAGRAM_ACCOUNT_REASON_MAP.get(reason, "unknown")


def _sanitize_media_url(value):
    if not isinstance(value, str):
        return None
    return value.replace("\\u0026", "&").replace("\\/", "/")


def _sanitize_description_text(value):
    if not isinstance(value, str):
        return None

    text = html.unescape(value).strip()
    if not text:
        return None

    if " on Instagram:" in text and '"' in text:
        first_quote = text.find('"')
        last_quote = text.rfind('"')
        if first_quote != -1 and last_quote > first_quote:
            quoted = text[first_quote + 1 : last_quote].strip()
            if quoted:
                text = quoted

    return text.strip()


def _get_streams_by_type(probe_info, codec_type):
    if not probe_info:
        return []
    return [stream for stream in probe_info.get("streams", []) if stream.get("codec_type") == codec_type]


def _probe_media_info(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return json.loads(result.stdout)
    except Exception as e:
        log(f"Не удалось получить media info через ffprobe: {e}", level="WARNING")
        return None


def _summarize_video_profile(path):
    probe_info = _probe_media_info(path)
    video_streams = _get_streams_by_type(probe_info, "video")
    audio_streams = _get_streams_by_type(probe_info, "audio")
    video_stream = video_streams[0] if video_streams else {}
    audio_stream = audio_streams[0] if audio_streams else {}
    format_info = (probe_info or {}).get("format", {})

    return {
        "probe_info": probe_info,
        "format_name": format_info.get("format_name"),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name") if audio_streams else None,
        "pix_fmt": video_stream.get("pix_fmt"),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "has_audio": bool(audio_streams),
    }


def _log_video_profile(label, path):
    profile = _summarize_video_profile(path)
    log(
        (
            f"{label}: format={profile['format_name'] or 'unknown'}, "
            f"vcodec={profile['video_codec'] or 'unknown'}, "
            f"acodec={profile['audio_codec'] or 'none'}, "
            f"pix_fmt={profile['pix_fmt'] or 'unknown'}, "
            f"size={profile['width']}x{profile['height']}"
        ),
        level="INFO",
    )
    return profile


def _video_needs_telegram_normalization(profile):
    if not profile or not profile.get("video_codec"):
        return True

    format_name = (profile.get("format_name") or "").lower()
    width = profile.get("width") or 0
    height = profile.get("height") or 0

    if "mp4" not in format_name:
        return True
    if profile.get("video_codec") not in TELEGRAM_SAFE_VIDEO_CODECS:
        return True
    if profile.get("audio_codec") not in TELEGRAM_SAFE_AUDIO_CODECS:
        return True
    if profile.get("pix_fmt") != "yuv420p":
        return True
    if width % 2 != 0 or height % 2 != 0:
        return True
    return False


def _normalize_video_for_telegram(input_path, temp_dir):
    profile = _log_video_profile("Instagram video before normalization", input_path)
    if not _video_needs_telegram_normalization(profile):
        return input_path

    output_path = os.path.join(temp_dir, "instagram_video_telegram.mp4")
    filter_chain = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    cmd = [
        "ffmpeg",
        "-fflags",
        "+genpts",
        "-i",
        input_path,
        "-map",
        "0:v:0",
    ]

    if profile.get("has_audio"):
        cmd.extend(["-map", "0:a:0?"])

    cmd.extend(
        [
            "-vf",
            filter_chain,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-profile:v",
            "high",
            "-level",
            "4.0",
        ]
    )

    if profile.get("has_audio"):
        cmd.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-ac",
                "2",
            ]
        )
    else:
        cmd.append("-an")

    cmd.extend(
        [
            "-max_muxing_queue_size",
            "1024",
            "-y",
            output_path,
        ]
    )

    with measure_time("CONVERT|instagram_video_normalize"):
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if process.returncode != 0 or not os.path.exists(output_path):
        stderr = (process.stderr or "").strip()
        raise RuntimeError(stderr or "ffmpeg не смог нормализовать Instagram видео")

    _log_video_profile("Instagram video after normalization", output_path)
    return output_path


def _extract_instagram_description_from_html(html_content):
    for pattern in HTML_DESCRIPTION_PATTERNS:
        matches = re.findall(pattern, html_content)
        if matches:
            description = _sanitize_description_text(matches[0])
            if description:
                return description
    return None


def _extract_instagram_description_from_info(info):
    if not isinstance(info, dict):
        return None

    candidates = [
        info.get("description"),
        info.get("title"),
        info.get("fulltitle"),
        info.get("caption"),
    ]

    for candidate in candidates:
        description = _sanitize_description_text(candidate)
        if description:
            return description
    return None


def _fetch_instagram_description_from_page(url):
    session = _create_session()
    try:
        for candidate in _instagram_variants(url):
            try:
                response = session.get(candidate, timeout=TIMEOUT, allow_redirects=True)
            except requests.RequestException as e:
                log(f"Ошибка при получении описания с {candidate}: {e}", level="WARNING")
                continue

            if not response.ok:
                continue

            description = _extract_instagram_description_from_html(response.text)
            if description:
                return description
    finally:
        session.close()

    return None


def _build_instagram_description_message(url, info):
    description = _extract_instagram_description_from_info(info)
    if not description:
        description = _fetch_instagram_description_from_page(url)
    if not description:
        return None

    source_url = url.split("?", 1)[0]
    text = f"📝 Описание рилса\n\n{description}\n\nСсылка: {source_url}"
    if len(text) > TELEGRAM_TEXT_LIMIT:
        overflow = len(text) - TELEGRAM_TEXT_LIMIT
        description_limit = max(0, len(description) - overflow - 3)
        description = description[:description_limit].rstrip() + "..."
        text = f"📝 Описание рилса\n\n{description}\n\nСсылка: {source_url}"
    return text


def _extract_media_from_html(html_content):
    for pattern in HTML_MEDIA_PATTERNS:
        matches = re.findall(pattern, html_content)
        if matches:
            media_url = _sanitize_media_url(matches[0])
            log(f"Найден URL видео: {media_url[:100]}...")
            return media_url
    return None


def _extract_media_from_json_payload(payload):
    candidates = []

    def visit(node):
        if isinstance(node, dict):
            for key in (
                "video_url",
                "contentUrl",
                "playable_url",
                "media_url",
                "video",
            ):
                value = node.get(key)
                if isinstance(value, str) and (".mp4" in value or "video" in key):
                    candidates.append(value)

            video_versions = node.get("video_versions")
            if isinstance(video_versions, list):
                for item in video_versions:
                    if isinstance(item, dict) and isinstance(item.get("url"), str):
                        candidates.append(item["url"])

            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)

    for candidate in candidates:
        media_url = _sanitize_media_url(candidate)
        if media_url:
            return media_url
    return None


def _instagram_variants(url):
    parsed = urlparse(url)
    if not parsed.netloc:
        return [url]

    hosts = [parsed.netloc]
    if parsed.netloc.startswith("www."):
        hosts.append(parsed.netloc.replace("www.", "", 1))
    elif parsed.netloc == "instagram.com":
        hosts.append("www.instagram.com")
    hosts.append("m.instagram.com")

    variants = []
    seen = set()
    for host in hosts:
        candidate = urlunparse(parsed._replace(netloc=host))
        if candidate not in seen:
            seen.add(candidate)
            variants.append(candidate)
    return variants


def _extract_info_with_yt_dlp(url):
    last_error = None
    last_reason = "unknown"
    for auth_label, auth_options in _iter_yt_dlp_auth_options():
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            try:
                options = _build_yt_dlp_options("video", download=False, auth_options=auth_options)
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception as e:
                last_error = e
                last_reason = _classify_instagram_error(e)
                log(
                    f"yt-dlp extract_info не сработал ({auth_label}, attempt {attempt}): {e}",
                    level="WARNING",
                )
                if attempt >= MAX_DOWNLOAD_ATTEMPTS or not _is_retryable_instagram_error(last_reason):
                    break
                _sleep_before_retry(f"extract_info {auth_label}", attempt)

        if last_reason == "auth_required":
            continue

    if last_error:
        raise InstagramUnavailableError(last_reason, last_error)
    raise InstagramUnavailableError("unknown", "Не удалось подготовить yt-dlp для Instagram")


def _extract_info_with_account(url):
    if not instagram_account_is_configured():
        return None
    if not instagram_account_supports_url(url):
        return None

    try:
        media = get_media_via_account(url)
        log("Instagram metadata получены через service account", level="INFO")
        return media.as_info_dict()
    except InstagramAccountError as e:
        mapped_reason = _map_account_reason(e.reason)
        log(
            f"Instagram service account не отдал metadata ({mapped_reason}): {e.detail or e.reason}",
            level="WARNING",
        )
        raise InstagramUnavailableError(mapped_reason, e.detail or e.reason) from e


def _download_with_yt_dlp(url, format_type="video"):
    last_error = None
    last_reason = "unknown"

    for auth_label, auth_options in _iter_yt_dlp_auth_options():
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            temp_dir = _create_temp_dir(f"instagram_{format_type}")
            try:
                options = _build_yt_dlp_options(
                    format_type,
                    temp_dir=temp_dir,
                    download=True,
                    auth_options=auth_options,
                )
                log(f"Пробую скачать Instagram {format_type} через yt-dlp ({auth_label}, attempt {attempt})")

                with measure_time(f"DOWNLOAD|instagram_{format_type}_ytdlp"):
                    with yt_dlp.YoutubeDL(options) as ydl:
                        info = ydl.extract_info(url, download=True)

                extension = ".mp3" if format_type == "audio" else None
                output_path = _find_downloaded_file(temp_dir, extension=extension)
                if not output_path:
                    raise RuntimeError("yt-dlp не создал выходной файл")

                file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                log_perf(f"FILE_SIZE|instagram_{format_type}_ytdlp|{file_size_mb:.2f}MB")
                return temp_dir, output_path, info
            except Exception as e:
                last_error = e
                last_reason = _classify_instagram_error(e)
                log(
                    f"Ошибка при скачивании через yt-dlp ({auth_label}, attempt {attempt}): {e}",
                    level="WARNING",
                )
                _cleanup_temp_dir(temp_dir)
                if attempt >= MAX_DOWNLOAD_ATTEMPTS or not _is_retryable_instagram_error(last_reason):
                    break
                _sleep_before_retry(f"download {auth_label}", attempt)

        if last_reason == "auth_required":
            continue

    if last_error:
        log(
            f"Все попытки yt-dlp для Instagram завершились ошибкой ({last_reason}): {last_error}",
            level="WARNING",
        )
        raise InstagramUnavailableError(last_reason, last_error)

    log("yt-dlp не получил ни одной стратегии скачивания Instagram", level="WARNING")
    raise InstagramUnavailableError("unknown", "yt-dlp не запустил ни одной стратегии")


def _download_video_with_account(url):
    if not instagram_account_is_configured():
        raise InstagramUnavailableError("not_configured", "Instagram account credentials are not configured")

    temp_dir = _create_temp_dir("instagram_account_video")
    try:
        output_path, info = download_video_via_account(url, temp_dir)
        if not output_path or not os.path.exists(output_path):
            raise InstagramUnavailableError("unknown", "Instagram account download did not create a file")

        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        log_perf(f"FILE_SIZE|instagram_video_account|{file_size_mb:.2f}MB")
        log("Instagram video получено через service account", level="INFO")
        return temp_dir, output_path, info
    except InstagramAccountError as e:
        _cleanup_temp_dir(temp_dir)
        raise InstagramUnavailableError(_map_account_reason(e.reason), e.detail or e.reason) from e
    except Exception as e:
        _cleanup_temp_dir(temp_dir)
        raise InstagramUnavailableError("unknown", e) from e


def _fetch_direct_media_url(url):
    session = _create_session()
    try:
        for candidate in _instagram_variants(url):
            try:
                with measure_time("CHECK|instagram_page_fetch"):
                    response = session.get(candidate, timeout=TIMEOUT, allow_redirects=True)
            except requests.RequestException as e:
                log(f"Ошибка при запросе к {candidate}: {e}", level="WARNING")
                continue

            if not response.ok:
                log(f"Instagram вернул статус {response.status_code} для {candidate}", level="WARNING")
                continue

            content_type = response.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                try:
                    media_url = _extract_media_from_json_payload(response.json())
                    if media_url:
                        return media_url
                except Exception as e:
                    log(f"Ошибка при разборе JSON Instagram: {e}", level="DEBUG")

            media_url = _extract_media_from_html(response.text)
            if media_url:
                return media_url

            try:
                json_match = re.search(r"window\._sharedData\s*=\s*({.+?});</script>", response.text)
                if json_match:
                    media_url = _extract_media_from_json_payload(json.loads(json_match.group(1)))
                    if media_url:
                        return media_url
            except Exception as e:
                log(f"Ошибка при извлечении embedded JSON: {e}", level="DEBUG")
    finally:
        session.close()

    return None


def _download_from_direct_media(url):
    media_url = _fetch_direct_media_url(url)
    if not media_url:
        return None, None, None

    session = _create_session()
    temp_dir = _create_temp_dir("instagram_direct")
    output_path = os.path.join(temp_dir, f"instagram_video_{int(time.time())}.mp4")

    try:
        with measure_time("DOWNLOAD|instagram_direct_media"):
            response = session.get(media_url, timeout=TIMEOUT, stream=True)
            response.raise_for_status()

        if response.headers.get("content-type", "").startswith("text/html"):
            raise RuntimeError("Вместо медиа получен HTML")

        with open(output_path, "wb") as output_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output_file.write(chunk)

        if not os.path.exists(output_path) or os.path.getsize(output_path) < 10240:
            raise RuntimeError("Прямое скачивание вернуло слишком маленький файл")

        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        log_perf(f"FILE_SIZE|instagram_video_direct|{file_size_mb:.2f}MB")
        return temp_dir, output_path, {}
    except Exception as e:
        log(f"Ошибка при прямом скачивании Instagram media: {e}", level="WARNING")
        _cleanup_temp_dir(temp_dir)
        return None, None, None
    finally:
        session.close()


def _download_instagram_video_asset(url):
    account_error = None
    if instagram_account_is_configured() and instagram_account_supports_url(url):
        try:
            return _download_video_with_account(url)
        except InstagramUnavailableError as e:
            account_error = e
            log(
                f"Instagram service account не смог скачать video ({e.reason}): {e.detail or e.reason}",
                level="WARNING",
            )

    try:
        return _download_with_yt_dlp(url, "video")
    except InstagramUnavailableError as e:
        if account_error and account_error.reason in {
            "account_auth_failed",
            "account_challenge_required",
            "account_two_factor_required",
        }:
            raise account_error
        if e.reason != "unknown":
            raise
        temp_dir, output_path, info = _download_from_direct_media(url)
        if output_path:
            return temp_dir, output_path, info
        if account_error:
            raise account_error
        raise


def _extract_audio_from_video_asset(temp_dir, video_path, info):
    if not video_path:
        raise InstagramUnavailableError("unknown", "Не удалось получить видео для извлечения аудио")

    audio_path = os.path.join(temp_dir, "instagram_audio.mp3")
    try:
        with measure_time("CONVERT|instagram_video_to_audio"):
            process = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    video_path,
                    "-vn",
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    "-y",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )

        if process.returncode != 0 or not os.path.exists(audio_path):
            raise RuntimeError(process.stderr or "ffmpeg не создал MP3")

        try:
            os.remove(video_path)
        except OSError:
            pass

        return temp_dir, audio_path, info
    except Exception as e:
        log(f"Ошибка при извлечении аудио из Instagram видео: {e}", level="ERROR")
        _cleanup_temp_dir(temp_dir)
        raise InstagramUnavailableError("unknown", e)


def _download_instagram_audio_asset(url):
    account_error = None
    if instagram_account_is_configured() and instagram_account_supports_url(url):
        try:
            temp_dir, video_path, info = _download_video_with_account(url)
            return _extract_audio_from_video_asset(temp_dir, video_path, info)
        except InstagramUnavailableError as e:
            account_error = e
            log(
                f"Instagram service account не смог подготовить audio ({e.reason}): {e.detail or e.reason}",
                level="WARNING",
            )

    try:
        return _download_with_yt_dlp(url, "audio")
    except InstagramUnavailableError as audio_error:
        if account_error and account_error.reason in {
            "account_auth_failed",
            "account_challenge_required",
            "account_two_factor_required",
        }:
            raise account_error
        if audio_error.reason not in {"unknown", "auth_required", "rate_limited"}:
            raise

    temp_dir, video_path, info = _download_instagram_video_asset(url)
    return _extract_audio_from_video_asset(temp_dir, video_path, info)


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


def _send_safe_instagram_failure(bot, chat_id, status_message_id, status_text, user_text):
    _finalize_status_message(bot, chat_id, status_message_id, status_text)
    bot.send_message(chat_id, user_text)


@perf_monitor
def check_instagram_availability(url):
    """Проверка доступности контента в Instagram."""
    log(f"Проверка доступности Instagram: {url}")
    if not is_instagram_url(url):
        log("Instagram контент недоступен: ссылка не поддерживается")
        return False

    # Для Instagram жесткий precheck вреден: он сам расходует лимит запросов и часто ломает
    # следующую реальную попытку скачивания. Разрешаем действие и проверяем доступ уже в download.
    log("Instagram precheck пропущен, чтобы не тратить лимиты до реального скачивания")
    return True


@perf_monitor
def download_instagram_video(bot, chat_id, url, message_id=None):
    """Скачивание видео из Instagram."""
    op_id = new_operation_id("ig-video")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Начинаю скачивание видео...")
    progress_stop = start_progress_message(bot, chat_id, "Скачивание видео с Instagram", status_message_id)
    temp_dir = None
    log_event("instagram_video_started", op=op_id, chat_id=chat_id, url=url)

    try:
        temp_dir, video_path, _ = _download_instagram_video_asset(url)
        try:
            normalized_path = _normalize_video_for_telegram(video_path, temp_dir)
            if normalized_path != video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except OSError:
                    pass
            video_path = normalized_path
        except Exception as e:
            log(f"Не удалось нормализовать Instagram видео под Telegram: {e}", level="WARNING")

        file_size = os.path.getsize(video_path)
        file_size_mb = file_size / (1024 * 1024)
        log_perf(f"FILE_SIZE|instagram_video|{file_size_mb:.2f}MB")

        if file_size > MAX_FILE_SIZE:
            _finalize_status_message(bot, chat_id, status_message_id, "⚠️ Видео оказалось слишком большим для Telegram.")
            log_event("instagram_video_rejected_large", op=op_id, chat_id=chat_id, size_mb=f"{file_size_mb:.2f}")
            bot.send_message(
                chat_id,
                f"⚠️ Видео слишком большое для отправки в Telegram ({file_size_mb:.2f} МБ > 50 МБ)",
            )
            return

        with measure_time("UPLOAD|instagram_video_upload"):
            with open(video_path, "rb") as video_file:
                sent_message = send_with_retry(
                    bot.send_video,
                    chat_id,
                    video_file,
                    caption="✅ Ваше видео из Instagram",
                )

        if sent_message is None:
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "❌ Не удалось отправить Instagram-видео в Telegram.",
            )
            log_event("instagram_video_upload_failed", level="ERROR", op=op_id, chat_id=chat_id)
            bot.send_message(chat_id, "❌ Не удалось отправить видео в Telegram.")
            return

        _finalize_status_message(bot, chat_id, status_message_id, "✅ Видео из Instagram успешно отправлено.")
        log_event("instagram_video_finished", op=op_id, chat_id=chat_id, size_mb=f"{file_size_mb:.2f}")
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except InstagramUnavailableError as e:
        user_message = _build_instagram_user_message(e.reason, action="скачать этот рилс")
        log_event(
            "instagram_video_unavailable",
            level="WARNING",
            op=op_id,
            chat_id=chat_id,
            reason=e.reason,
            error=e.detail or e.reason,
        )
        _finalize_status_message(bot, chat_id, status_message_id, f"⚠️ {user_message}")
        bot.send_message(chat_id, f"⚠️ {user_message}")
    except Exception as e:
        log_event("instagram_video_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _send_safe_instagram_failure(
            bot,
            chat_id,
            status_message_id,
            "❌ Не удалось обработать Instagram-видео.",
            "❌ Не удалось скачать или отправить видео из Instagram. Попробуйте ещё раз чуть позже.",
        )
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)


@perf_monitor
def download_instagram_audio(bot, chat_id, url, message_id=None):
    """Извлечение аудио из видео в Instagram."""
    op_id = new_operation_id("ig-audio")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Извлекаю аудио...")
    progress_stop = start_progress_message(bot, chat_id, "Извлечение аудио из Instagram", status_message_id)
    temp_dir = None
    log_event("instagram_audio_started", op=op_id, chat_id=chat_id, url=url)

    try:
        temp_dir, audio_path, info = _download_instagram_audio_asset(url)

        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        log_perf(f"FILE_SIZE|instagram_audio|{file_size_mb:.2f}MB")

        if file_size > MAX_FILE_SIZE:
            _finalize_status_message(bot, chat_id, status_message_id, "⚠️ Аудио оказалось слишком большим для Telegram.")
            log_event("instagram_audio_rejected_large", op=op_id, chat_id=chat_id, size_mb=f"{file_size_mb:.2f}")
            bot.send_message(
                chat_id,
                f"⚠️ Аудио слишком большое для отправки в Telegram ({file_size_mb:.2f} МБ > 50 МБ)",
            )
            return

        title = "Instagram Audio"
        performer = None
        if info:
            title = info.get("track") or info.get("title") or title
            performer = info.get("artist") or info.get("uploader")

        send_kwargs = {
            "caption": "✅ Ваше аудио из Instagram",
            "title": title,
        }
        if performer:
            send_kwargs["performer"] = performer

        with measure_time("UPLOAD|instagram_audio_upload"):
            with open(audio_path, "rb") as audio_file:
                sent_message = send_with_retry(
                    bot.send_audio,
                    chat_id,
                    audio_file,
                    **send_kwargs,
                )

        if sent_message is None:
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "❌ Не удалось отправить Instagram-аудио в Telegram.",
            )
            log_event("instagram_audio_upload_failed", level="ERROR", op=op_id, chat_id=chat_id)
            bot.send_message(chat_id, "❌ Не удалось отправить аудио в Telegram.")
            return

        _finalize_status_message(bot, chat_id, status_message_id, "✅ Аудио из Instagram успешно отправлено.")
        log_event("instagram_audio_finished", op=op_id, chat_id=chat_id, size_mb=f"{file_size_mb:.2f}")
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except InstagramUnavailableError as e:
        user_message = _build_instagram_user_message(e.reason, action="получить аудио из этого рилса")
        log_event(
            "instagram_audio_unavailable",
            level="WARNING",
            op=op_id,
            chat_id=chat_id,
            reason=e.reason,
            error=e.detail or e.reason,
        )
        _finalize_status_message(bot, chat_id, status_message_id, f"⚠️ {user_message}")
        bot.send_message(chat_id, f"⚠️ {user_message}")
    except Exception as e:
        log_event("instagram_audio_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _send_safe_instagram_failure(
            bot,
            chat_id,
            status_message_id,
            "❌ Не удалось обработать Instagram-аудио.",
            "❌ Не удалось извлечь или отправить аудио из Instagram. Попробуйте ещё раз чуть позже.",
        )
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)


@perf_monitor
def download_instagram_description(bot, chat_id, url, message_id=None):
    """Отправка текстового описания Instagram reel."""
    op_id = new_operation_id("ig-description")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Получаю описание рилса...")
    progress_stop = start_progress_message(bot, chat_id, "Получение описания из Instagram", status_message_id)
    log_event("instagram_description_started", op=op_id, chat_id=chat_id, url=url)

    try:
        info = None
        last_unavailable_error = None
        try:
            info = _extract_info_with_account(url)
        except InstagramUnavailableError as e:
            last_unavailable_error = e
            log(
                f"Не удалось получить описание через service account ({e.reason}): {e.detail or e.reason}",
                level="WARNING",
            )
        if not info:
            try:
                info = _extract_info_with_yt_dlp(url)
            except InstagramUnavailableError as e:
                last_unavailable_error = e
                log(
                    f"Не удалось получить описание через yt-dlp ({e.reason}): {e.detail or e.reason}",
                    level="WARNING",
                )
        text = _build_instagram_description_message(url, info)
        if not text:
            if last_unavailable_error and last_unavailable_error.reason != "unsupported_url":
                user_message = _build_instagram_user_message(
                    last_unavailable_error.reason,
                    action="получить описание по этой Instagram-ссылке",
                )
                _finalize_status_message(bot, chat_id, status_message_id, f"⚠️ {user_message}")
                log_event(
                    "instagram_description_unavailable",
                    level="WARNING",
                    op=op_id,
                    chat_id=chat_id,
                    reason=last_unavailable_error.reason,
                    error=last_unavailable_error.detail or last_unavailable_error.reason,
                )
                bot.send_message(chat_id, f"⚠️ {user_message}")
                return

            _finalize_status_message(bot, chat_id, status_message_id, "⚠️ Описание у этого рилса не найдено.")
            log_event("instagram_description_missing", level="WARNING", op=op_id, chat_id=chat_id)
            bot.send_message(chat_id, "⚠️ Не удалось найти описание у этого рилса.")
            return

        bot.send_message(
            chat_id,
            text,
            link_preview_options=types.LinkPreviewOptions(is_disabled=True),
        )
        _finalize_status_message(bot, chat_id, status_message_id, "✅ Описание рилса отправлено.")
        log_event("instagram_description_finished", op=op_id, chat_id=chat_id)
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except Exception as e:
        log_event("instagram_description_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _send_safe_instagram_failure(
            bot,
            chat_id,
            status_message_id,
            "❌ Не удалось получить описание рилса.",
            "❌ Не удалось получить описание рилса. Попробуйте ещё раз чуть позже.",
        )
    finally:
        progress_stop.set()


@perf_monitor
def transcribe_instagram_reel(bot, chat_id, url, message_id=None):
    """Расшифровка Instagram reel через OpenAI без саммари."""
    op_id = new_operation_id("ig-transcript")
    status_message_id = _ensure_status_message(bot, chat_id, message_id, "⏳ Запускаю расшифровку рилса...")
    progress_stop = start_progress_message(bot, chat_id, "Расшифровка Instagram рилса", status_message_id)
    temp_dir = None
    log_event("instagram_transcription_started", op=op_id, chat_id=chat_id, url=url)

    try:
        if not OPENAI_API_KEY:
            _finalize_status_message(bot, chat_id, status_message_id, "❌ Не настроен OpenAI API key.")
            bot.send_message(
                chat_id,
                "❌ Для расшифровки нужен `OPENAI_API_KEY` в конфиге бота.",
                parse_mode="Markdown",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Скачиваю аудио рилса для расшифровки...")
        temp_dir, audio_path, _ = _download_instagram_audio_asset(url)

        audio_size = os.path.getsize(audio_path)
        audio_size_mb = audio_size / (1024 * 1024)
        log_event(
            "instagram_transcription_audio_ready",
            op=op_id,
            chat_id=chat_id,
            size_mb=f"{audio_size_mb:.2f}",
        )
        if audio_size > OPENAI_TRANSCRIPTION_FILE_LIMIT:
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "⚠️ Рилс слишком длинный для автоматической расшифровки.",
            )
            bot.send_message(
                chat_id,
                "⚠️ Аудио оказалось слишком большим для транскрипции через OpenAI "
                f"({audio_size_mb:.2f} МБ > 25 МБ). "
                "Попробуйте более короткий рилс.",
            )
            return

        _ensure_status_message(bot, chat_id, status_message_id, "⏳ Распознаю речь через OpenAI...")
        with measure_time("OPENAI|instagram_audio_transcription"):
            transcript_text = transcribe_audio_with_openai(audio_path)

        if not transcript_text:
            log_event(
                "instagram_transcription_empty",
                level="WARNING",
                op=op_id,
                chat_id=chat_id,
                size_mb=f"{audio_size_mb:.2f}",
            )
            _finalize_status_message(
                bot,
                chat_id,
                status_message_id,
                "⚠️ В рилсе не удалось распознать речь.",
            )
            bot.send_message(
                chat_id,
                "⚠️ OpenAI не нашёл распознаваемой речи в этом рилсе. "
                "Возможно, там музыка, шум, очень короткий фрагмент или речь слышно слишком слабо.",
            )
            return

        transcript_chunks = split_text_chunks(transcript_text)
        log_event(
            "instagram_transcription_chunking",
            op=op_id,
            chat_id=chat_id,
            chunks=len(transcript_chunks),
        )

        send_text_chunks(bot, chat_id, transcript_text)
        _finalize_status_message(bot, chat_id, status_message_id, "✅ Расшифровка рилса готова.")
        log_event("instagram_transcription_finished", op=op_id, chat_id=chat_id)
        bot.send_message(chat_id, READY_FOR_MORE_TEXT)
    except InstagramUnavailableError as e:
        user_message = _build_instagram_user_message(e.reason, action="расшифровать этот рилс")
        log_event(
            "instagram_transcription_unavailable",
            level="WARNING",
            op=op_id,
            chat_id=chat_id,
            reason=e.reason,
            error=e.detail or e.reason,
        )
        _finalize_status_message(bot, chat_id, status_message_id, f"⚠️ {user_message}")
        bot.send_message(chat_id, f"⚠️ {user_message}")
    except OpenAITemporaryError as e:
        log_event("instagram_transcription_openai_unavailable", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ OpenAI временно недоступен.")
        bot.send_message(
            chat_id, "❌ Не удалось связаться с OpenAI при расшифровке рилса. Попробуйте ещё раз чуть позже."
        )
    except requests.HTTPError as e:
        log_event("instagram_transcription_http_error", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _finalize_status_message(bot, chat_id, status_message_id, "❌ Не удалось получить расшифровку.")
        bot.send_message(chat_id, "❌ OpenAI API вернул ошибку при расшифровке рилса.")
    except Exception as e:
        log_event("instagram_transcription_failed", level="ERROR", op=op_id, chat_id=chat_id, error=e)
        _send_safe_instagram_failure(
            bot,
            chat_id,
            status_message_id,
            "❌ Не удалось расшифровать рилс.",
            "❌ Не удалось подготовить расшифровку рилса. Попробуйте ещё раз чуть позже.",
        )
    finally:
        progress_stop.set()
        _cleanup_temp_dir(temp_dir)
