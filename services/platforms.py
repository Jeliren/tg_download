import re
from urllib.parse import parse_qs, urlparse

YOUTUBE = "youtube"
INSTAGRAM = "instagram"

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
}

INSTAGRAM_MEDIA_PATTERNS = (
    re.compile(r"^/(p|reel|reels|tv)/[^/?#]+/?$"),
    re.compile(r"^/stories/[^/?#]+/[^/?#]+/?$"),
)


def normalize_url(text):
    if not text:
        return None

    candidate = text.strip()
    if not candidate:
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None

    return candidate


def detect_platform(text):
    normalized = normalize_url(text)
    if not normalized:
        return None

    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query)

    if host in YOUTUBE_HOSTS:
        if host.endswith("youtu.be") and path.strip("/"):
            return YOUTUBE
        if path.startswith("/watch") and query.get("v"):
            return YOUTUBE
        if path.startswith("/shorts/") or path.startswith("/live/") or path.startswith("/embed/"):
            return YOUTUBE

    if host in INSTAGRAM_HOSTS:
        for pattern in INSTAGRAM_MEDIA_PATTERNS:
            if pattern.match(path):
                return INSTAGRAM

    return None


def is_youtube_url(text):
    return detect_platform(text) == YOUTUBE


def is_instagram_url(text):
    return detect_platform(text) == INSTAGRAM
