import unittest
from unittest import mock

from services import uploaded_video_service


class UploadedVideoServiceRuntimeTests(unittest.TestCase):
    def test_transcribe_uploaded_video_sends_transcript_text(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with mock.patch.object(
            uploaded_video_service,
            "OPENAI_API_KEY",
            "test-key",
        ), mock.patch.object(
            uploaded_video_service,
            "start_progress_message",
            return_value=stop_event,
        ), mock.patch.object(
            uploaded_video_service,
            "check_ffmpeg",
            return_value=True,
        ), mock.patch.object(
            uploaded_video_service,
            "_prepare_uploaded_video_audio",
            return_value="/tmp/uploaded/audio.mp3",
        ), mock.patch(
            "services.uploaded_video_service.os.path.getsize",
            return_value=1024,
        ), mock.patch.object(
            uploaded_video_service,
            "transcribe_audio_with_openai",
            return_value="текст видео",
        ), mock.patch.object(
            uploaded_video_service,
            "send_text_chunks",
        ) as send_text_chunks:
            uploaded_video_service.transcribe_uploaded_video(
                bot,
                chat_id=42,
                user_id=7,
                video_file_id="telegram-file-id",
                message_id=100,
            )

        send_text_chunks.assert_called_once_with(bot, 42, "текст видео")
        self.assertTrue(
            any(
                call.args == (42, uploaded_video_service.READY_FOR_MORE_TEXT)
                for call in bot.send_message.call_args_list
            )
        )
        stop_event.set.assert_called_once()

    def test_summarize_uploaded_video_sends_summary_text(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with mock.patch.object(
            uploaded_video_service,
            "OPENAI_API_KEY",
            "test-key",
        ), mock.patch.object(
            uploaded_video_service,
            "start_progress_message",
            return_value=stop_event,
        ), mock.patch.object(
            uploaded_video_service,
            "check_ffmpeg",
            return_value=True,
        ), mock.patch.object(
            uploaded_video_service,
            "_prepare_uploaded_video_audio",
            return_value="/tmp/uploaded/audio.mp3",
        ), mock.patch(
            "services.uploaded_video_service.os.path.getsize",
            return_value=1024,
        ), mock.patch.object(
            uploaded_video_service,
            "transcribe_audio_with_openai",
            return_value="текст видео",
        ), mock.patch.object(
            uploaded_video_service,
            "count_summary_chunks",
            return_value=1,
        ), mock.patch.object(
            uploaded_video_service,
            "summarize_transcript_text",
            return_value="готовое саммари",
        ):
            uploaded_video_service.summarize_uploaded_video(
                bot,
                chat_id=42,
                user_id=7,
                video_file_id="telegram-file-id",
                message_id=100,
            )

        self.assertTrue(
            any(
                "готовое саммари" in call.args[1]
                for call in bot.send_message.call_args_list
                if len(call.args) > 1
            )
        )
        self.assertTrue(
            any(
                call.args == (42, uploaded_video_service.READY_FOR_MORE_TEXT)
                for call in bot.send_message.call_args_list
            )
        )
        stop_event.set.assert_called_once()
