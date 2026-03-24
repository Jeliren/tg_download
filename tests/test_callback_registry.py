import unittest
from types import SimpleNamespace

from bot.callback_registry import CallbackRegistry


class CallbackRegistryTests(unittest.TestCase):
    def test_register_and_resolve_action_url(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        key = registry.register_action_url("https://youtu.be/test")

        self.assertEqual(registry.resolve_action_url(key), "https://youtu.be/test")

    def test_register_and_resolve_format_url(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        key = registry.register_format_url("https://www.youtube.com/watch?v=test")

        self.assertEqual(
            registry.resolve_format_url(key),
            "https://www.youtube.com/watch?v=test",
        )

    def test_register_and_resolve_format_selection(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        key = registry.register_format_selection(
            "https://www.youtube.com/watch?v=test",
            "bv*[height<=?720]+ba/b[height<=?720]",
        )

        self.assertEqual(
            registry.resolve_format_selection(key),
            {
                "url": "https://www.youtube.com/watch?v=test",
                "format_id": "bv*[height<=?720]+ba/b[height<=?720]",
            },
        )

    def test_register_and_resolve_music_search(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60, music_ttl=60)
        key = registry.register_music_search(
            7,
            "daft punk",
            [{"url": "https://www.youtube.com/watch?v=test", "display_title": "Daft Punk - One More Time"}],
        )

        self.assertEqual(
            registry.resolve_music_search(key),
            {
                "user_id": 7,
                "query": "daft punk",
                "results": [
                    {
                        "url": "https://www.youtube.com/watch?v=test",
                        "display_title": "Daft Punk - One More Time",
                    }
                ],
            },
        )

    def test_register_and_resolve_uploaded_video(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        key = registry.register_uploaded_video(
            {
                "chat_id": 42,
                "message_id": 100,
                "file_id": "telegram-file-id",
                "user_id": 7,
            }
        )

        self.assertEqual(
            registry.resolve_uploaded_video(key),
            {
                "chat_id": 42,
                "message_id": 100,
                "file_id": "telegram-file-id",
                "user_id": 7,
                "media_type": "video",
            },
        )

    def test_register_and_resolve_uploaded_audio(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        key = registry.register_uploaded_audio(
            {
                "chat_id": 42,
                "message_id": 100,
                "file_id": "telegram-audio-file-id",
                "user_id": 7,
            }
        )

        self.assertEqual(
            registry.resolve_uploaded_audio(key),
            {
                "chat_id": 42,
                "message_id": 100,
                "file_id": "telegram-audio-file-id",
                "user_id": 7,
                "media_type": "audio",
            },
        )

    def test_register_and_resolve_uploaded_voice(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        key = registry.register_uploaded_voice(
            {
                "chat_id": 42,
                "message_id": 100,
                "file_id": "telegram-voice-file-id",
                "user_id": 7,
            }
        )

        self.assertEqual(
            registry.resolve_uploaded_voice(key),
            {
                "chat_id": 42,
                "message_id": 100,
                "file_id": "telegram-voice-file-id",
                "user_id": 7,
                "media_type": "voice",
            },
        )

    def test_register_uploaded_audio_ignores_empty_video_attribute(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=42),
            message_id=100,
            from_user=SimpleNamespace(id=7),
            video=None,
            audio=SimpleNamespace(file_id="telegram-audio-file-id"),
            voice=None,
        )

        key = registry.register_uploaded_audio(message)

        self.assertEqual(
            registry.resolve_uploaded_audio(key),
            {
                "chat_id": 42,
                "message_id": 100,
                "file_id": "telegram-audio-file-id",
                "user_id": 7,
                "media_type": "audio",
            },
        )

    def test_register_uploaded_audio_accepts_document_payload(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=42),
            message_id=101,
            from_user=SimpleNamespace(id=7),
            video=None,
            audio=None,
            voice=None,
            document=SimpleNamespace(file_id="telegram-document-audio-id"),
        )

        key = registry.register_uploaded_audio(message)

        self.assertEqual(
            registry.resolve_uploaded_audio(key),
            {
                "chat_id": 42,
                "message_id": 101,
                "file_id": "telegram-document-audio-id",
                "user_id": 7,
                "media_type": "audio",
            },
        )

    def test_register_uploaded_video_accepts_document_payload(self):
        registry = CallbackRegistry(url_ttl=60, format_ttl=60)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=42),
            message_id=102,
            from_user=SimpleNamespace(id=7),
            video=None,
            audio=None,
            voice=None,
            document=SimpleNamespace(file_id="telegram-document-video-id"),
        )

        key = registry.register_uploaded_video(message)

        self.assertEqual(
            registry.resolve_uploaded_video(key),
            {
                "chat_id": 42,
                "message_id": 102,
                "file_id": "telegram-document-video-id",
                "user_id": 7,
                "media_type": "video",
            },
        )


if __name__ == "__main__":
    unittest.main()
