import unittest
from unittest import mock

from services import converter_service


class ConverterServiceTests(unittest.TestCase):
    def test_builds_high_quality_video_note_command(self):
        cmd = converter_service._build_video_note_ffmpeg_command(
            "/tmp/input.mp4",
            "/tmp/output.mp4",
            "crop=720:720:0:280",
            {"scale": 512, "crf": 21, "preset": "medium", "audio": True, "audio_bitrate": "112k"},
        )

        joined = " ".join(cmd)
        self.assertIn("crop=720:720:0:280,scale=512:512:flags=lanczos", joined)
        self.assertIn("-crf 21", joined)
        self.assertIn("-c:a aac", joined)
        self.assertIn("-b:a 112k", joined)

    def test_builds_silent_fallback_video_note_command(self):
        cmd = converter_service._build_video_note_ffmpeg_command(
            "/tmp/input.mp4",
            "/tmp/output.mp4",
            "crop=720:720:0:280",
            {"scale": 384, "crf": 28, "preset": "fast", "audio": False, "audio_bitrate": "0"},
        )

        self.assertIn("-an", cmd)
        self.assertNotIn("-c:a", cmd)

    def test_builds_voice_message_command(self):
        cmd = converter_service._build_voice_message_ffmpeg_command(
            "/tmp/input.mp3",
            "/tmp/output.ogg",
        )

        joined = " ".join(cmd)
        self.assertIn("-c:a libopus", joined)
        self.assertIn("-application voip", joined)
        self.assertIn("-ac 1", joined)
        self.assertIn("/tmp/output.ogg", joined)

    def test_video_note_converter_fails_fast_when_ffmpeg_missing(self):
        bot = mock.Mock()

        with mock.patch.object(
            converter_service,
            "check_ffmpeg",
            return_value=False,
        ):
            result = converter_service.convert_video_file_to_video_note(
                bot,
                chat_id=42,
                user_id=7,
                video_file_id="telegram-file-id",
            )

        self.assertFalse(result)
        bot.send_message.assert_called_once_with(42, "❌ Для обработки видео нужен ffmpeg.")


if __name__ == "__main__":
    unittest.main()
