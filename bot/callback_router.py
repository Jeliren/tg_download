"""Классификация callback payload-ов Telegram для bot.handlers."""

from dataclasses import dataclass

CALLBACK_ROUTE_UNKNOWN = "unknown"
CALLBACK_ROUTE_DOWNLOAD = "download"
CALLBACK_ROUTE_UPLOADED_VIDEO = "uploaded_video"
CALLBACK_ROUTE_UPLOADED_AUDIO = "uploaded_audio"
CALLBACK_ROUTE_FORMAT = "format"
CALLBACK_ROUTE_MUSIC = "music"

__all__ = [
    "CALLBACK_ROUTE_DOWNLOAD",
    "CALLBACK_ROUTE_FORMAT",
    "CALLBACK_ROUTE_MUSIC",
    "CALLBACK_ROUTE_UNKNOWN",
    "CALLBACK_ROUTE_UPLOADED_AUDIO",
    "CALLBACK_ROUTE_UPLOADED_VIDEO",
    "CallbackRoute",
    "classify_callback_data",
]

DOWNLOAD_ACTIONS = {"v", "a", "d", "s", "t", "tr", "x"}
UPLOADED_VIDEO_ACTIONS = {"vn", "vt", "vs"}
UPLOADED_AUDIO_ACTIONS = {"an", "at", "as"}
MUSIC_ACTIONS = {"mp", "ms"}

ACTION_KIND_MAP = {
    **{action: CALLBACK_ROUTE_DOWNLOAD for action in DOWNLOAD_ACTIONS},
    **{action: CALLBACK_ROUTE_UPLOADED_VIDEO for action in UPLOADED_VIDEO_ACTIONS},
    **{action: CALLBACK_ROUTE_UPLOADED_AUDIO for action in UPLOADED_AUDIO_ACTIONS},
    **{action: CALLBACK_ROUTE_MUSIC for action in MUSIC_ACTIONS},
    "f": CALLBACK_ROUTE_FORMAT,
}


@dataclass(frozen=True)
class CallbackRoute:
    kind: str
    action: str | None = None
    raw_data: str | None = None


def classify_callback_data(data):
    """Возвращает нормализованный route для callback_data."""
    normalized = (data or "").strip()
    if not normalized:
        return CallbackRoute(CALLBACK_ROUTE_UNKNOWN, raw_data=data)

    action = normalized.split(":", 1)[0]
    return CallbackRoute(
        ACTION_KIND_MAP.get(action, CALLBACK_ROUTE_UNKNOWN),
        action=action,
        raw_data=normalized,
    )
