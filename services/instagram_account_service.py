from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from types import MethodType
from urllib.parse import urlparse

from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ChallengeRequired,
    ChallengeSelfieCaptcha,
    ChallengeUnknownStep,
    ClientForbiddenError,
    ClientLoginRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
    TwoFactorRequired,
)

from config import (
    EXTERNAL_CONNECT_TIMEOUT,
    EXTERNAL_READ_TIMEOUT,
    INSTAGRAM_ACCOUNT_SESSION_FILE,
    INSTAGRAM_PASSWORD,
    INSTAGRAM_USERNAME,
)
from core.cache import ExpiringStore
from utils.logging_utils import log

__all__ = [
    "InstagramAccountError",
    "InstagramAccountMedia",
    "download_video_via_account",
    "get_media_via_account",
    "instagram_account_supports_url",
    "instagram_account_is_configured",
]


LOGIN_EXCEPTIONS = (LoginRequired, ClientLoginRequired)
CHALLENGE_EXCEPTIONS = (
    ChallengeRequired,
    ChallengeSelfieCaptcha,
    ChallengeUnknownStep,
    TwoFactorRequired,
)
SHORTCODE_PATH_PREFIXES = {"p", "reel", "reels", "tv"}


@dataclass
class InstagramAccountMedia:
    media_pk: str
    caption_text: str | None
    title: str | None
    video_url: str | None
    username: str | None
    product_type: str | None

    def as_info_dict(self):
        return {
            "description": self.caption_text,
            "title": self.title,
            "uploader": self.username,
            "video_url": self.video_url,
            "product_type": self.product_type,
        }


class InstagramAccountError(RuntimeError):
    def __init__(self, reason, detail=None):
        self.reason = reason or "unknown"
        self.detail = str(detail or "").strip()
        super().__init__(self.detail or self.reason)


_CLIENT_LOCK = threading.Lock()
_CLIENT = None
_MEDIA_CACHE = ExpiringStore(ttl=60 * 10)


def instagram_account_is_configured():
    return bool(INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD)


def _build_client():
    client = Client()
    client.request_timeout = EXTERNAL_CONNECT_TIMEOUT + EXTERNAL_READ_TIMEOUT
    default_timeout = (EXTERNAL_CONNECT_TIMEOUT, EXTERNAL_READ_TIMEOUT)

    def request_with_timeout(session, method, url, **kwargs):
        kwargs.setdefault("timeout", default_timeout)
        return session.__class__.request(session, method, url, **kwargs)

    client.private.request = MethodType(request_with_timeout, client.private)
    client.public.request = MethodType(request_with_timeout, client.public)
    return client


def _settings_path():
    return INSTAGRAM_ACCOUNT_SESSION_FILE


def _shortcode_from_url(url):
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    if parts[0] not in SHORTCODE_PATH_PREFIXES:
        return None
    return parts[1]


def instagram_account_supports_url(url):
    return _shortcode_from_url(url) is not None


def _media_cache_key(url):
    shortcode = _shortcode_from_url(url)
    return f"shortcode:{shortcode}" if shortcode else url


def _ensure_settings_parent_dir():
    settings_path = _settings_path()
    parent_dir = os.path.dirname(settings_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)


def _classify_account_exception(error):
    if isinstance(error, BadPassword):
        return "bad_credentials"
    if isinstance(error, TwoFactorRequired):
        return "two_factor_required"
    if isinstance(error, CHALLENGE_EXCEPTIONS):
        return "challenge_required"
    if isinstance(error, PleaseWaitFewMinutes):
        return "rate_limited"
    if isinstance(error, (ClientForbiddenError, *LOGIN_EXCEPTIONS)):
        return "login_required"

    text = str(error).lower()
    if "challenge" in text:
        return "challenge_required"
    if "two-factor" in text or "two factor" in text:
        return "two_factor_required"
    if "wait a few minutes" in text or "please wait" in text:
        return "rate_limited"
    if "login required" in text:
        return "login_required"
    return "unknown"


def _save_client_settings(client):
    _ensure_settings_parent_dir()
    client.dump_settings(_settings_path())


def _fresh_login_client():
    client = _build_client()
    client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    client.get_timeline_feed()
    _save_client_settings(client)
    return client


def _login_client():
    settings_path = _settings_path()
    if settings_path and os.path.exists(settings_path):
        client = _build_client()
        try:
            client.load_settings(settings_path)
            client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            client.get_timeline_feed()
            _save_client_settings(client)
            log("Instagram account session restored from saved settings", level="INFO")
            return client
        except LOGIN_EXCEPTIONS as e:
            log(f"Instagram saved session requires relogin: {e}", level="WARNING")
        except Exception as e:
            log(f"Не удалось восстановить Instagram account session: {e}", level="WARNING")

    return _fresh_login_client()


def _get_client(force_relogin=False):
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None and not force_relogin:
            return _CLIENT

        if not instagram_account_is_configured():
            raise InstagramAccountError("not_configured", "Instagram account credentials are not configured")

        try:
            _CLIENT = _login_client()
        except Exception as e:
            raise InstagramAccountError(_classify_account_exception(e), e) from e
        return _CLIENT


def _invalidate_client():
    global _CLIENT
    with _CLIENT_LOCK:
        _CLIENT = None


def _extract_media_payload(client, url):
    shortcode = _shortcode_from_url(url)
    if not shortcode:
        raise InstagramAccountError("unknown", "Instagram URL does not contain a shortcode")

    media_pk = client.media_pk_from_code(shortcode)
    media = client.media_info_v1(media_pk)
    username = getattr(getattr(media, "user", None), "username", None)
    caption_text = media.caption_text or None
    title = media.title or caption_text or None
    video_url = media.video_url or None

    if not video_url and media.resources:
        for resource in media.resources:
            resource_video_url = getattr(resource, "video_url", None)
            if resource_video_url:
                video_url = str(resource_video_url)
                break

    return InstagramAccountMedia(
        media_pk=str(media_pk),
        caption_text=caption_text,
        title=title,
        video_url=str(video_url) if video_url else None,
        username=username,
        product_type=media.product_type or None,
    )


def _run_with_client(action, *, allow_relogin=True):
    last_error = None

    for attempt in range(2):
        force_relogin = attempt == 1 and allow_relogin
        client = _get_client(force_relogin=force_relogin)
        try:
            return action(client)
        except Exception as e:
            last_error = e
            reason = _classify_account_exception(e)
            if reason == "login_required" and allow_relogin and attempt == 0:
                _invalidate_client()
                continue
            raise InstagramAccountError(reason, e) from e

    raise InstagramAccountError(_classify_account_exception(last_error), last_error)


def get_media_via_account(url):
    if not instagram_account_is_configured():
        raise InstagramAccountError("not_configured", "Instagram account credentials are not configured")
    if not instagram_account_supports_url(url):
        raise InstagramAccountError(
            "unsupported_url",
            "Instagram account mode currently supports reel/post/tv URLs only",
        )

    cache_key = _media_cache_key(url)
    cached_payload = _MEDIA_CACHE.get(cache_key)
    if cached_payload is not None:
        log("Instagram metadata получены из локального cache", level="DEBUG")
        return cached_payload

    payload = _run_with_client(lambda client: _extract_media_payload(client, url))
    _MEDIA_CACHE.set(cache_key, payload)
    return payload


def download_video_via_account(url, temp_dir):
    if not instagram_account_is_configured():
        raise InstagramAccountError("not_configured", "Instagram account credentials are not configured")
    if not instagram_account_supports_url(url):
        raise InstagramAccountError(
            "unsupported_url",
            "Instagram account mode currently supports reel/post/tv URLs only",
        )

    payload = get_media_via_account(url)

    def action(client):
        if not payload.video_url:
            raise InstagramAccountError("video_missing", "Instagram account session did not return video_url")

        filename = f"instagram_account_video_{int(time.time())}"
        output_path = client.video_download_by_url(payload.video_url, filename=filename, folder=temp_dir)
        return str(output_path), payload.as_info_dict()

    return _run_with_client(action)
