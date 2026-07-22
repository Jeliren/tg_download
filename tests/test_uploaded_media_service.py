import os
import unittest
from unittest import mock

from services import uploaded_media_service


class UploadedMediaServiceTests(unittest.TestCase):
    def test_convert_audio_to_mp3_builds_openai_compatible_command(self):
        completed = mock.Mock(returncode=0, stderr="")

        with mock.patch.object(uploaded_media_service.subprocess, "run", return_value=completed) as run:
            result = uploaded_media_service.convert_audio_to_mp3(
                "/tmp/input.oga",
                "/tmp/output.mp3",
            )

        command = run.call_args.args[0]
        self.assertEqual(result, "/tmp/output.mp3")
        self.assertEqual(command[command.index("-i") + 1], "/tmp/input.oga")
        self.assertIn("mp3", command)
        self.assertIn("-ac", command)
        self.assertEqual(command[-1], "/tmp/output.mp3")

    def test_prepare_uploaded_audio_converts_telegram_oga_to_mp3(self):
        bot = mock.Mock()

        with (
            mock.patch.object(
                uploaded_media_service,
                "download_telegram_file",
                return_value="/tmp/job/uploaded_audio.oga",
            ) as download,
            mock.patch.object(
                uploaded_media_service,
                "convert_audio_to_mp3",
                return_value="/tmp/job/uploaded_audio_prepared.mp3",
            ) as convert,
        ):
            result = uploaded_media_service.prepare_uploaded_audio(
                bot,
                "telegram-file-id",
                "/tmp/job",
            )

        download.assert_called_once_with(
            bot,
            "telegram-file-id",
            "/tmp/job",
            "uploaded_audio",
            default_extension=".mp3",
        )
        convert.assert_called_once_with(
            "/tmp/job/uploaded_audio.oga",
            os.path.join("/tmp/job", "uploaded_audio_prepared.mp3"),
        )
        self.assertEqual(result, "/tmp/job/uploaded_audio_prepared.mp3")


if __name__ == "__main__":
    unittest.main()
