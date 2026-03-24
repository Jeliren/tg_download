"""Реестр payload-ов для коротких Telegram callback_data."""

import hashlib
import uuid

from config import URL_CACHE_TTL
from core.cache import ExpiringStore


class CallbackRegistry:
    """Реестр данных для коротких callback payload Telegram."""

    def __init__(self, url_ttl=URL_CACHE_TTL, format_ttl=URL_CACHE_TTL, music_ttl=URL_CACHE_TTL):
        self._action_urls = ExpiringStore(ttl=url_ttl)
        self._format_urls = ExpiringStore(ttl=format_ttl)
        self._format_selections = ExpiringStore(ttl=format_ttl)
        self._uploaded_media = ExpiringStore(ttl=url_ttl)
        self._music_searches = ExpiringStore(ttl=music_ttl)

    def register_action_url(self, url):
        url_id = uuid.uuid4().hex[:8]
        self._action_urls.set(url_id, url)
        return url_id

    def resolve_action_url(self, url_id):
        return self._action_urls.get(url_id)

    def _build_uploaded_payload(self, message, media_object, media_type):
        return {
            "chat_id": getattr(getattr(message, "chat", None), "id", None),
            "message_id": getattr(message, "message_id", None),
            "file_id": getattr(media_object, "file_id", None),
            "user_id": getattr(getattr(message, "from_user", None), "id", None),
            "media_type": media_type,
        }

    def register_uploaded_media(self, payload, media_type=None):
        video = getattr(payload, "video", None)
        audio = getattr(payload, "audio", None)
        voice = getattr(payload, "voice", None)
        document = getattr(payload, "document", None)

        if video is not None:
            payload = self._build_uploaded_payload(payload, video, "video")
        elif audio is not None:
            payload = self._build_uploaded_payload(payload, audio, "audio")
        elif voice is not None:
            payload = self._build_uploaded_payload(payload, voice, "voice")
        elif document is not None and media_type == "audio":
            payload = self._build_uploaded_payload(payload, document, "audio")
        elif document is not None and media_type == "video":
            payload = self._build_uploaded_payload(payload, document, "video")
        elif media_type and isinstance(payload, dict):
            payload = {**payload, "media_type": payload.get("media_type") or media_type}

        media_id = uuid.uuid4().hex[:10]
        self._uploaded_media.set(media_id, payload)
        return media_id

    def resolve_uploaded_media(self, media_id):
        return self._uploaded_media.get(media_id)

    def register_uploaded_video(self, payload):
        return self.register_uploaded_media(payload, media_type="video")

    def register_uploaded_audio(self, payload):
        return self.register_uploaded_media(payload, media_type="audio")

    def register_uploaded_voice(self, payload):
        return self.register_uploaded_media(payload, media_type="voice")

    def resolve_uploaded_video(self, video_id):
        return self.resolve_uploaded_media(video_id)

    def resolve_uploaded_audio(self, audio_id):
        return self.resolve_uploaded_media(audio_id)

    def resolve_uploaded_voice(self, voice_id):
        return self.resolve_uploaded_media(voice_id)

    def register_format_url(self, url):
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
        self._format_urls.set(url_hash, url)
        return url_hash

    def resolve_format_url(self, url_hash):
        return self._format_urls.get(url_hash)

    def register_format_selection(self, url, format_id):
        selection_id = uuid.uuid4().hex[:10]
        self._format_selections.set(
            selection_id,
            {
                "url": url,
                "format_id": format_id,
            },
        )
        return selection_id

    def resolve_format_selection(self, selection_id):
        return self._format_selections.get(selection_id)

    def register_music_search(self, user_id, query, results):
        search_id = uuid.uuid4().hex[:10]
        self._music_searches.set(
            search_id,
            {
                "user_id": user_id,
                "query": query,
                "results": results,
            },
        )
        return search_id

    def resolve_music_search(self, search_id):
        return self._music_searches.get(search_id)


callback_registry = CallbackRegistry()
