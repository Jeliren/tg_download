"""Поиск музыки на YouTube для сценария bot.handlers."""

from __future__ import annotations

import re
from typing import Any

import yt_dlp

from utils.logging_utils import log

MAX_MUSIC_RESULTS = 15
_TITLE_SPLIT_RE = re.compile(r"\s[-–—]\s", re.UNICODE)
_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")

_POSITIVE_KEYWORDS = {
    "official audio": 14,
    "official video": 8,
    "audio": 5,
    "lyrics": 3,
    "topic": 5,
    "provided to youtube": 5,
    "music video": 3,
}
_NEGATIVE_KEYWORDS = {
    "full album": 10,
    "podcast": 12,
    "interview": 10,
    "reaction": 12,
    "karaoke": 10,
    "cover": 4,
}


class MusicSearchError(RuntimeError):
    """Ошибки поиска музыки с готовым user-facing сообщением."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def _base_search_options() -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _truncate_text(text: str, limit: int) -> str:
    normalized = _clean_text(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


def _format_duration(seconds: Any) -> str | None:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return None

    total_seconds = int(seconds)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _extract_split_title(title: str) -> tuple[str | None, str | None]:
    parts = _TITLE_SPLIT_RE.split(_clean_text(title), maxsplit=1)
    if len(parts) != 2:
        return None, None

    artist_part = _clean_text(parts[0])
    track_part = _clean_text(parts[1])
    if not artist_part or not track_part:
        return None, None
    return artist_part, track_part


def _extract_artist(entry: dict[str, Any], title: str) -> str | None:
    for key in ("artist", "album_artist", "creator"):
        value = _clean_text(entry.get(key))
        if value:
            return value

    split_artist, _ = _extract_split_title(title)
    if split_artist:
        return split_artist

    uploader = _clean_text(entry.get("uploader") or entry.get("channel"))
    if uploader.endswith(" - Topic"):
        return uploader[: -len(" - Topic")].strip() or None
    return None


def _extract_track(entry: dict[str, Any], title: str) -> str | None:
    for key in ("track", "alt_title"):
        value = _clean_text(entry.get(key))
        if value:
            return value

    _, split_track = _extract_split_title(title)
    return split_track


def _build_video_url(entry: dict[str, Any]) -> str | None:
    webpage_url = _clean_text(entry.get("webpage_url") or entry.get("url"))
    if webpage_url.startswith("http://") or webpage_url.startswith("https://"):
        return webpage_url
    if webpage_url.startswith("/watch"):
        return f"https://www.youtube.com{webpage_url}"
    if _YOUTUBE_VIDEO_ID_RE.fullmatch(webpage_url):
        return f"https://www.youtube.com/watch?v={webpage_url}"

    video_id = _clean_text(entry.get("id"))
    if _YOUTUBE_VIDEO_ID_RE.fullmatch(video_id):
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def _score_entry(entry: dict[str, Any], artist: str | None, track: str | None, title: str) -> int:
    haystack = " ".join(
        filter(
            None,
            [
                _clean_text(title).lower(),
                _clean_text(entry.get("uploader")).lower(),
                _clean_text(entry.get("channel")).lower(),
            ],
        )
    )
    score = 0
    if _clean_text(entry.get("artist")):
        score += 16
    if _clean_text(entry.get("track")):
        score += 16
    if artist and track:
        score += 8

    for keyword, value in _POSITIVE_KEYWORDS.items():
        if keyword in haystack:
            score += value
    for keyword, penalty in _NEGATIVE_KEYWORDS.items():
        if keyword in haystack:
            score -= penalty

    return score


def _format_display_title(artist: str | None, track: str | None, title: str) -> str:
    if artist and track:
        return f"{artist} - {track}"
    return _clean_text(title)


def _normalize_entry(entry: dict[str, Any], position: int) -> dict[str, Any] | None:
    title = _clean_text(entry.get("title"))
    if not title:
        return None

    video_url = _build_video_url(entry)
    if not video_url:
        return None

    artist = _extract_artist(entry, title)
    track = _extract_track(entry, title)
    display_title = _format_display_title(artist, track, title)

    return {
        "url": video_url,
        "title": title,
        "artist": artist,
        "track": track,
        "duration": entry.get("duration"),
        "duration_label": _format_duration(entry.get("duration")),
        "display_title": display_title,
        "button_label": _truncate_text(display_title, 60),
        "score": _score_entry(entry, artist, track, title),
        "position": position,
    }


def search_music(query: str, *, max_results: int = MAX_MUSIC_RESULTS) -> list[dict[str, Any]]:
    """Ищет музыкальные результаты на YouTube и нормализует их для UI."""
    normalized_query = _clean_text(query)
    if not normalized_query:
        return []

    limit = max(1, min(max_results, MAX_MUSIC_RESULTS))
    search_term = f"ytsearch{limit}:{normalized_query}"

    try:
        with yt_dlp.YoutubeDL(_base_search_options()) as ydl:
            info = ydl.extract_info(search_term, download=False) or {}
    except Exception as exc:
        log(f"Ошибка поиска музыки на YouTube: {exc}", level="WARNING")
        raise MusicSearchError(
            "❌ Поиск музыки временно недоступен. Попробуйте ещё раз чуть позже.",
        ) from exc

    normalized_results = []
    for position, entry in enumerate(info.get("entries") or []):
        normalized_entry = _normalize_entry(entry or {}, position)
        if normalized_entry:
            normalized_results.append(normalized_entry)

    normalized_results.sort(key=lambda item: (-item["score"], item["position"]))
    return normalized_results[:limit]
