import unittest
from unittest import mock

from services import uploaded_audio_service
from services.openai_client import OpenAITemporaryError


class UploadedAudioServiceRuntimeTests(unittest.TestCase):
    def test_transcribe_uploaded_audio_sends_transcript_text(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with (
            mock.patch.object(
                uploaded_audio_service,
                "OPENAI_API_KEY",
                "test-key",
            ),
            mock.patch.object(
                uploaded_audio_service,
                "start_progress_message",
                return_value=stop_event,
            ),
            mock.patch.object(
                uploaded_audio_service,
                "_prepare_uploaded_audio",
                return_value="/tmp/uploaded/audio.mp3",
            ),
            mock.patch(
                "services.uploaded_audio_service.os.path.getsize",
                return_value=1024,
            ),
            mock.patch.object(
                uploaded_audio_service,
                "transcribe_audio_with_openai",
                return_value="текст аудио",
            ),
            mock.patch.object(
                uploaded_audio_service,
                "send_text_chunks",
            ) as send_text_chunks,
        ):
            uploaded_audio_service.transcribe_uploaded_audio(
                bot,
                chat_id=42,
                user_id=7,
                audio_file_id="telegram-audio-file-id",
                message_id=100,
            )

        send_text_chunks.assert_called_once_with(bot, 42, "текст аудио")
        self.assertTrue(
            any(
                call.args == (42, uploaded_audio_service.READY_FOR_MORE_TEXT)
                for call in bot.send_message.call_args_list
            )
        )
        stop_event.set.assert_called_once()

    def test_transcribe_uploaded_audio_reports_temporary_openai_failure(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with (
            mock.patch.object(
                uploaded_audio_service,
                "OPENAI_API_KEY",
                "test-key",
            ),
            mock.patch.object(
                uploaded_audio_service,
                "start_progress_message",
                return_value=stop_event,
            ),
            mock.patch.object(
                uploaded_audio_service,
                "_prepare_uploaded_audio",
                return_value="/tmp/uploaded/audio.mp3",
            ),
            mock.patch(
                "services.uploaded_audio_service.os.path.getsize",
                return_value=1024,
            ),
            mock.patch.object(
                uploaded_audio_service,
                "transcribe_audio_with_openai",
                side_effect=OpenAITemporaryError("audio/transcriptions", "timeout"),
            ),
        ):
            uploaded_audio_service.transcribe_uploaded_audio(
                bot,
                chat_id=42,
                user_id=7,
                audio_file_id="telegram-audio-file-id",
                message_id=100,
            )

        bot.edit_message_text.assert_any_call(
            "❌ OpenAI временно недоступен.",
            chat_id=42,
            message_id=100,
        )
        self.assertTrue(
            any(
                "Не удалось связаться с OpenAI" in call.args[1]
                for call in bot.send_message.call_args_list
                if len(call.args) > 1
            )
        )
        stop_event.set.assert_called_once()

    def test_summarize_uploaded_audio_sends_summary_text(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with (
            mock.patch.object(
                uploaded_audio_service,
                "OPENAI_API_KEY",
                "test-key",
            ),
            mock.patch.object(
                uploaded_audio_service,
                "start_progress_message",
                return_value=stop_event,
            ),
            mock.patch.object(
                uploaded_audio_service,
                "_prepare_uploaded_audio",
                return_value="/tmp/uploaded/audio.mp3",
            ),
            mock.patch(
                "services.uploaded_audio_service.os.path.getsize",
                return_value=1024,
            ),
            mock.patch.object(
                uploaded_audio_service,
                "transcribe_audio_with_openai",
                return_value="текст аудио",
            ),
            mock.patch.object(
                uploaded_audio_service,
                "count_summary_chunks",
                return_value=1,
            ),
            mock.patch.object(
                uploaded_audio_service,
                "summarize_transcript_text",
                return_value="готовое саммари",
            ),
        ):
            uploaded_audio_service.summarize_uploaded_audio(
                bot,
                chat_id=42,
                user_id=7,
                audio_file_id="telegram-audio-file-id",
                message_id=100,
            )

        self.assertTrue(
            any("готовое саммари" in call.args[1] for call in bot.send_message.call_args_list if len(call.args) > 1)
        )
        self.assertTrue(
            any(
                call.args == (42, uploaded_audio_service.READY_FOR_MORE_TEXT)
                for call in bot.send_message.call_args_list
            )
        )
        stop_event.set.assert_called_once()
