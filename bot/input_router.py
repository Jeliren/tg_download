"""Классификация входящих Telegram-сообщений для bot.handlers."""

from dataclasses import dataclass

from services.platforms import INSTAGRAM, YOUTUBE, detect_platform

ROUTE_UNKNOWN = "unknown"
ROUTE_YOUTUBE_URL = "youtube_url"
ROUTE_INSTAGRAM_URL = "instagram_url"
ROUTE_UPLOADED_VIDEO = "uploaded_video"
ROUTE_UPLOADED_AUDIO = "uploaded_audio"
ROUTE_UPLOADED_VOICE = "uploaded_voice"

__all__ = [
    "ROUTE_INSTAGRAM_URL",
    "ROUTE_UNKNOWN",
    "ROUTE_UPLOADED_AUDIO",
    "ROUTE_UPLOADED_VIDEO",
    "ROUTE_UPLOADED_VOICE",
    "ROUTE_YOUTUBE_URL",
    "IncomingMessageRoute",
    "classify_message",
    "is_audio_document",
    "is_video_document",
]

AUDIO_DOCUMENT_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".flac",
    ".m4a",
    ".mp3",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}
VIDEO_DOCUMENT_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}


@dataclass(frozen=True)
class IncomingMessageRoute:
    kind: str
    file_id: str | None = None
    text: str | None = None


def _document_matches(document, mime_prefix, extensions):
    if document is None:
        return False

    mime_type = (getattr(document, "mime_type", None) or "").lower()
    if mime_type.startswith(mime_prefix):
        return True

    file_name = (getattr(document, "file_name", None) or "").lower()
    return any(file_name.endswith(extension) for extension in extensions)


def is_audio_document(message):
    return _document_matches(
        getattr(message, "document", None),
        "audio/",
        AUDIO_DOCUMENT_EXTENSIONS,
    )


def is_video_document(message):
    return _document_matches(
        getattr(message, "document", None),
        "video/",
        VIDEO_DOCUMENT_EXTENSIONS,
    )


def classify_message(message):
    """Возвращает нормализованный route для входящего Telegram message."""
    video = getattr(message, "video", None)
    if video is not None:
        return IncomingMessageRoute(ROUTE_UPLOADED_VIDEO, file_id=getattr(video, "file_id", None))

    audio = getattr(message, "audio", None)
    if audio is not None:
        return IncomingMessageRoute(ROUTE_UPLOADED_AUDIO, file_id=getattr(audio, "file_id", None))

    voice = getattr(message, "voice", None)
    if voice is not None:
        return IncomingMessageRoute(ROUTE_UPLOADED_VOICE, file_id=getattr(voice, "file_id", None))

    document = getattr(message, "document", None)
    if document is not None:
        if is_audio_document(message):
            return IncomingMessageRoute(ROUTE_UPLOADED_AUDIO, file_id=getattr(document, "file_id", None))
        if is_video_document(message):
            return IncomingMessageRoute(ROUTE_UPLOADED_VIDEO, file_id=getattr(document, "file_id", None))

    text = (getattr(message, "text", None) or "").strip()
    if text:
        platform = detect_platform(text)
        if platform == YOUTUBE:
            return IncomingMessageRoute(ROUTE_YOUTUBE_URL, text=text)
        if platform == INSTAGRAM:
            return IncomingMessageRoute(ROUTE_INSTAGRAM_URL, text=text)

    return IncomingMessageRoute(ROUTE_UNKNOWN)
