import unittest
from types import SimpleNamespace

from bot.input_router import (
    ROUTE_INSTAGRAM_URL,
    ROUTE_UNKNOWN,
    ROUTE_UPLOADED_AUDIO,
    ROUTE_UPLOADED_VIDEO,
    ROUTE_UPLOADED_VOICE,
    ROUTE_YOUTUBE_URL,
    classify_message,
)


class InputRouterTests(unittest.TestCase):
    def test_classifies_uploaded_video(self):
        message = SimpleNamespace(video=SimpleNamespace(file_id="video-file-id"))

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_UPLOADED_VIDEO)
        self.assertEqual(route.file_id, "video-file-id")

    def test_classifies_uploaded_audio(self):
        message = SimpleNamespace(audio=SimpleNamespace(file_id="audio-file-id"))

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_UPLOADED_AUDIO)
        self.assertEqual(route.file_id, "audio-file-id")

    def test_classifies_uploaded_voice(self):
        message = SimpleNamespace(voice=SimpleNamespace(file_id="voice-file-id"))

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_UPLOADED_VOICE)
        self.assertEqual(route.file_id, "voice-file-id")

    def test_classifies_audio_document(self):
        message = SimpleNamespace(
            video=None,
            audio=None,
            voice=None,
            document=SimpleNamespace(file_id="doc-audio-id", mime_type="audio/mpeg", file_name="track.bin"),
        )

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_UPLOADED_AUDIO)
        self.assertEqual(route.file_id, "doc-audio-id")

    def test_classifies_video_document(self):
        message = SimpleNamespace(
            video=None,
            audio=None,
            voice=None,
            document=SimpleNamespace(
                file_id="doc-video-id",
                mime_type="application/octet-stream",
                file_name="clip.mp4",
            ),
        )

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_UPLOADED_VIDEO)
        self.assertEqual(route.file_id, "doc-video-id")

    def test_classifies_youtube_text(self):
        message = SimpleNamespace(
            video=None,
            audio=None,
            voice=None,
            document=None,
            text="https://youtu.be/abc123",
        )

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_YOUTUBE_URL)
        self.assertEqual(route.text, "https://youtu.be/abc123")

    def test_classifies_instagram_text(self):
        message = SimpleNamespace(
            video=None,
            audio=None,
            voice=None,
            document=None,
            text="https://www.instagram.com/reel/ABC123/",
        )

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_INSTAGRAM_URL)
        self.assertEqual(route.text, "https://www.instagram.com/reel/ABC123/")

    def test_classifies_unknown_message(self):
        message = SimpleNamespace(
            video=None,
            audio=None,
            voice=None,
            document=SimpleNamespace(file_id="doc-id", mime_type="application/pdf", file_name="file.pdf"),
            text=None,
        )

        route = classify_message(message)

        self.assertEqual(route.kind, ROUTE_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
