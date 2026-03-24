import unittest
from types import SimpleNamespace
from unittest import mock

from bot.handlers import BotHandlerCoordinator
from bot.texts import INVALID_UPLOADED_MEDIA_TEXT, MUSIC_PROMPT_TEXT, WAIT_PREVIOUS_OPERATION_TEXT


class HandlerCoordinatorTests(unittest.TestCase):
    def test_handle_video_shows_action_buttons_instead_of_starting_conversion(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=321,
            video=SimpleNamespace(file_id="telegram-file-id"),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.register_uploaded_video",
            return_value="vid1234567",
        ) as register_video, mock.patch(
            "bot.handlers.create_uploaded_video_markup",
            return_value="markup",
        ) as create_markup, mock.patch.object(
            coordinator,
            "_submit_background_task",
        ) as submit_task:
            coordinator.handle_video(message)

        register_video.assert_called_once_with(
            {
                "chat_id": 55,
                "message_id": 321,
                "file_id": "telegram-file-id",
                "user_id": 77,
            }
        )
        create_markup.assert_called_once_with("vid1234567")
        bot.reply_to.assert_called_once_with(
            message,
            "🎬 Что сделать с этим видео?",
            reply_markup="markup",
        )
        submit_task.assert_not_called()

    def test_handle_audio_shows_action_buttons(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=322,
            audio=SimpleNamespace(file_id="telegram-audio-file-id"),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.register_uploaded_audio",
            return_value="aud1234567",
        ) as register_audio, mock.patch(
            "bot.handlers.create_uploaded_audio_markup",
            return_value="markup",
        ) as create_markup, mock.patch.object(
            coordinator,
            "_submit_background_task",
        ) as submit_task:
            coordinator.handle_audio(message)

        register_audio.assert_called_once_with(
            {
                "chat_id": 55,
                "message_id": 322,
                "file_id": "telegram-audio-file-id",
                "user_id": 77,
            }
        )
        create_markup.assert_called_once_with("aud1234567")
        bot.reply_to.assert_called_once_with(
            message,
            "🎵 Что сделать с этим аудио?",
            reply_markup="markup",
        )
        submit_task.assert_not_called()

    def test_handle_voice_shows_only_transcript_and_summary_buttons(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=323,
            voice=SimpleNamespace(file_id="telegram-voice-file-id"),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.register_uploaded_voice",
            return_value="voc1234567",
        ) as register_voice, mock.patch(
            "bot.handlers.create_uploaded_voice_markup",
            return_value="markup",
        ) as create_markup, mock.patch.object(
            coordinator,
            "_submit_background_task",
        ) as submit_task:
            coordinator.handle_voice(message)

        register_voice.assert_called_once_with(
            {
                "chat_id": 55,
                "message_id": 323,
                "file_id": "telegram-voice-file-id",
                "user_id": 77,
            }
        )
        create_markup.assert_called_once_with("voc1234567")
        bot.reply_to.assert_called_once_with(
            message,
            "🎙 Что сделать с этим голосовым сообщением?",
            reply_markup="markup",
        )
        submit_task.assert_not_called()

    def test_handle_document_audio_by_mime_shows_audio_actions(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=324,
            document=SimpleNamespace(file_id="telegram-doc-audio-id", mime_type="audio/mpeg", file_name="track.bin"),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.register_uploaded_audio",
            return_value="auddoc1234",
        ) as register_audio, mock.patch(
            "bot.handlers.create_uploaded_audio_markup",
            return_value="markup",
        ) as create_markup:
            coordinator.handle_document(message)

        register_audio.assert_called_once_with(
            {
                "chat_id": 55,
                "message_id": 324,
                "file_id": "telegram-doc-audio-id",
                "user_id": 77,
            }
        )
        create_markup.assert_called_once_with("auddoc1234")
        bot.reply_to.assert_called_once_with(
            message,
            "🎵 Что сделать с этим аудиофайлом?",
            reply_markup="markup",
        )

    def test_handle_document_audio_by_extension_shows_audio_actions(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=325,
            document=SimpleNamespace(
                file_id="telegram-doc-audio-id",
                mime_type="application/octet-stream",
                file_name="track.m4a",
            ),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.register_uploaded_audio",
            return_value="auddoc5678",
        ) as register_audio, mock.patch(
            "bot.handlers.create_uploaded_audio_markup",
            return_value="markup",
        ) as create_markup:
            coordinator.handle_document(message)

        register_audio.assert_called_once_with(
            {
                "chat_id": 55,
                "message_id": 325,
                "file_id": "telegram-doc-audio-id",
                "user_id": 77,
            }
        )
        create_markup.assert_called_once_with("auddoc5678")
        bot.reply_to.assert_called_once_with(
            message,
            "🎵 Что сделать с этим аудиофайлом?",
            reply_markup="markup",
        )

    def test_handle_document_video_by_mime_shows_video_actions(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=326,
            document=SimpleNamespace(file_id="telegram-doc-video-id", mime_type="video/mp4", file_name="clip.bin"),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.register_uploaded_video",
            return_value="viddoc1234",
        ) as register_video, mock.patch(
            "bot.handlers.create_uploaded_video_markup",
            return_value="markup",
        ) as create_markup:
            coordinator.handle_document(message)

        register_video.assert_called_once_with(
            {
                "chat_id": 55,
                "message_id": 326,
                "file_id": "telegram-doc-video-id",
                "user_id": 77,
            }
        )
        create_markup.assert_called_once_with("viddoc1234")
        bot.reply_to.assert_called_once_with(
            message,
            "🎬 Что сделать с этим видеофайлом?",
            reply_markup="markup",
        )

    def test_handle_document_video_by_extension_shows_video_actions(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=327,
            document=SimpleNamespace(
                file_id="telegram-doc-video-id",
                mime_type="application/octet-stream",
                file_name="clip.mov",
            ),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.register_uploaded_video",
            return_value="viddoc5678",
        ) as register_video, mock.patch(
            "bot.handlers.create_uploaded_video_markup",
            return_value="markup",
        ) as create_markup:
            coordinator.handle_document(message)

        register_video.assert_called_once_with(
            {
                "chat_id": 55,
                "message_id": 327,
                "file_id": "telegram-doc-video-id",
                "user_id": 77,
            }
        )
        create_markup.assert_called_once_with("viddoc5678")
        bot.reply_to.assert_called_once_with(
            message,
            "🎬 Что сделать с этим видеофайлом?",
            reply_markup="markup",
        )

    def test_handle_non_audio_document_falls_back_to_unknown_command(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=328,
            document=SimpleNamespace(file_id="telegram-doc-id", mime_type="application/pdf", file_name="file.pdf"),
            from_user=SimpleNamespace(id=77),
        )

        coordinator.handle_document(message)

        bot.reply_to.assert_called_once_with(message, mock.ANY)

    def test_handle_uploaded_media_without_file_id_reports_clear_error(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=329,
            audio=SimpleNamespace(file_id=None),
            from_user=SimpleNamespace(id=77),
        )

        coordinator.handle_audio(message)

        bot.reply_to.assert_called_once_with(message, INVALID_UPLOADED_MEDIA_TEXT)

    def test_music_button_enters_music_mode(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=330,
            text="Музыка",
            from_user=SimpleNamespace(id=77),
        )

        coordinator.handle_text_message(message)

        bot.reply_to.assert_called_once_with(
            message,
            MUSIC_PROMPT_TEXT,
            reply_markup=mock.ANY,
        )
        self.assertTrue(coordinator.runtime.music_query_state.contains(77))

    def test_waiting_music_query_submits_search_task(self):
        bot = mock.Mock()
        bot.reply_to.return_value = SimpleNamespace(message_id=401, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)
        coordinator.runtime.music_query_state.set(77, True)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=331,
            text="Daft Punk - One More Time",
            from_user=SimpleNamespace(id=77),
            video=None,
            audio=None,
            voice=None,
            document=None,
        )

        with mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator.handle_text_message(message)

        submit_task.assert_called_once_with(
            "music_search",
            coordinator._perform_music_search,
            55,
            77,
            "Daft Punk - One More Time",
            401,
        )

    def test_waiting_music_query_does_not_intercept_youtube_url(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        coordinator.runtime.music_query_state.set(77, True)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=332,
            text="https://youtu.be/abc123",
            from_user=SimpleNamespace(id=77),
            video=None,
            audio=None,
            voice=None,
            document=None,
        )

        with mock.patch.object(coordinator, "_handle_youtube_url") as handle_youtube:
            coordinator.handle_text_message(message)

        handle_youtube.assert_called_once_with(message, "https://youtu.be/abc123")

    def test_music_query_is_blocked_while_user_has_active_task(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        coordinator.runtime.music_query_state.set(77, True)
        message = SimpleNamespace(
            chat=SimpleNamespace(id=55),
            message_id=333,
            text="Massive Attack",
            from_user=SimpleNamespace(id=77),
            video=None,
            audio=None,
            voice=None,
            document=None,
        )

        with mock.patch.object(coordinator.runtime.active_users, "is_active", return_value=True):
            coordinator.handle_text_message(message)

        bot.reply_to.assert_called_once_with(message, WAIT_PREVIOUS_OPERATION_TEXT)

    def test_download_callback_blocks_parallel_user_task(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)

        call = SimpleNamespace(
            id="cb-busy",
            data="v:url123",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_action_url",
            return_value="https://www.youtube.com/watch?v=abc123",
        ), mock.patch.object(
            coordinator.runtime.active_users,
            "try_start",
            return_value=False,
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
        ) as submit_task:
            coordinator._handle_download_callback(call, "v")

        submit_task.assert_not_called()
        bot.answer_callback_query.assert_called_once_with("cb-busy", text=mock.ANY)

    def test_handle_callback_routes_download_action_through_callback_router(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        call = SimpleNamespace(
            id="cb-router-download",
            data="v:url123",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch.object(coordinator, "_handle_download_callback") as handle_download:
            coordinator.handle_callback(call)

        handle_download.assert_called_once_with(call, "v")

    def test_paid_summary_callback_submits_transcription_flow(self):
        bot = mock.Mock()
        bot.send_message.return_value = SimpleNamespace(message_id=889, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)

        call = SimpleNamespace(
            id="cb-paid-summary",
            data="t:url123",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_action_url",
            return_value="https://www.youtube.com/watch?v=abc123",
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_download_callback(call, "t")

        submit_task.assert_called_once_with(
            "youtube_summary_with_transcription",
            coordinator._handle_summary_with_transcription_download,
            55,
            "https://www.youtube.com/watch?v=abc123",
            889,
        )

    def test_cancel_paid_summary_callback_sends_message(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)

        call = SimpleNamespace(
            id="cb-cancel-summary",
            data="x:url123",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_action_url",
            return_value="https://www.youtube.com/watch?v=abc123",
        ):
            coordinator._handle_download_callback(call, "x")

        bot.send_message.assert_called_once()

    def test_summary_callback_keeps_original_button_message_untouched(self):
        bot = mock.Mock()
        bot.send_message.return_value = SimpleNamespace(message_id=888, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)

        call = SimpleNamespace(
            id="cb-summary",
            data="s:url123",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_action_url",
            return_value="https://www.youtube.com/watch?v=abc123",
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_download_callback(call, "s")

        submit_task.assert_called_once_with(
            "youtube_summary",
            coordinator._handle_summary_download,
            55,
            "https://www.youtube.com/watch?v=abc123",
            888,
        )
        bot.edit_message_text.assert_not_called()

    def test_description_callback_keeps_original_button_message_untouched(self):
        bot = mock.Mock()
        bot.send_message.return_value = SimpleNamespace(message_id=777, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)

        call = SimpleNamespace(
            id="cb-1",
            data="d:url123",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_action_url",
            return_value="https://www.instagram.com/reel/ABC123/?igsh=1",
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_download_callback(call, "d")

        submit_task.assert_called_once_with(
            "description_download",
            coordinator._handle_description_download,
            55,
            "https://www.instagram.com/reel/ABC123/?igsh=1",
            777,
        )
        bot.edit_message_text.assert_not_called()

    def test_transcription_callback_submits_instagram_transcription_flow(self):
        bot = mock.Mock()
        bot.send_message.return_value = SimpleNamespace(message_id=778, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)

        call = SimpleNamespace(
            id="cb-transcript",
            data="tr:url123",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_action_url",
            return_value="https://www.instagram.com/reel/ABC123/?igsh=1",
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_download_callback(call, "tr")

        submit_task.assert_called_once_with(
            "instagram_transcription",
            coordinator._handle_transcription_download,
            55,
            "https://www.instagram.com/reel/ABC123/?igsh=1",
            778,
        )
        bot.edit_message_text.assert_not_called()

    def test_process_url_uses_soft_instagram_availability_flow(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)

        with mock.patch(
            "bot.handlers.instagram_service.check_instagram_availability",
            return_value=True,
        ) as check_mock, mock.patch.object(
            coordinator,
            "_create_and_show_buttons",
        ) as create_buttons:
            coordinator._process_url(
                chat_id=55,
                url="https://www.instagram.com/reel/ABC123/?igsh=1",
                message_id=123,
            )

        check_mock.assert_called_once_with("https://www.instagram.com/reel/ABC123/?igsh=1")
        create_buttons.assert_called_once_with(55, "https://www.instagram.com/reel/ABC123/?igsh=1", 123)

    def test_format_callback_supports_short_registry_payload(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)

        call = SimpleNamespace(
            id="cb-2",
            data="f:fmt1234567",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=321),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_format_selection",
            return_value={
                "url": "https://www.youtube.com/watch?v=abc123",
                "format_id": "best",
            },
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_format_callback(call)

        submit_task.assert_called_once_with(
            "youtube_format_download",
            mock.ANY,
            bot,
            55,
            "https://www.youtube.com/watch?v=abc123",
            321,
            "best",
        )

    def test_uploaded_video_summary_callback_submits_summary_flow(self):
        bot = mock.Mock()
        bot.send_message.return_value = SimpleNamespace(message_id=901, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)
        payload = {
            "chat_id": 55,
            "message_id": 321,
            "file_id": "telegram-file-id",
            "user_id": 77,
        }

        call = SimpleNamespace(
            id="cb-video-summary",
            data="vs:vid1234567",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=654),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_uploaded_video",
            return_value=payload,
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_uploaded_video_callback(call, "vs")

        submit_task.assert_called_once_with(
            "uploaded_video_summary",
            coordinator._handle_uploaded_video_summary,
            payload,
            901,
        )

    def test_uploaded_audio_summary_callback_submits_summary_flow(self):
        bot = mock.Mock()
        bot.send_message.return_value = SimpleNamespace(message_id=902, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)
        payload = {
            "chat_id": 55,
            "message_id": 322,
            "file_id": "telegram-audio-file-id",
            "user_id": 77,
            "media_type": "audio",
        }

        call = SimpleNamespace(
            id="cb-audio-summary",
            data="as:aud1234567",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=655),
            from_user=SimpleNamespace(id=77),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_uploaded_audio",
            return_value=payload,
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_uploaded_audio_callback(call, "as")

        submit_task.assert_called_once_with(
            "uploaded_audio_summary",
            coordinator._handle_uploaded_audio_summary,
            payload,
            902,
        )

    def test_perform_music_search_updates_message_with_results(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)

        with mock.patch(
            "bot.handlers.music_service.search_music",
            return_value=[
                {
                    "url": "https://www.youtube.com/watch?v=one",
                    "display_title": "Artist - Track",
                    "button_label": "Artist - Track",
                    "duration_label": "3:33",
                }
            ],
        ), mock.patch(
            "bot.handlers.callback_registry.register_music_search",
            return_value="music123",
        ):
            coordinator._perform_music_search(55, 77, "artist track", 700)

        bot.edit_message_text.assert_called_once()
        self.assertFalse(coordinator.runtime.music_query_state.contains(77))

    def test_perform_music_search_keeps_waiting_state_on_no_results(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)

        with mock.patch("bot.handlers.music_service.search_music", return_value=[]):
            coordinator._perform_music_search(55, 77, "zzz", 701)

        bot.edit_message_text.assert_called_once_with(
            text=mock.ANY,
            chat_id=55,
            message_id=701,
            reply_markup=None,
        )
        self.assertTrue(coordinator.runtime.music_query_state.contains(77))

    def test_music_page_callback_updates_existing_results_message(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        call = SimpleNamespace(
            id="cb-music-page",
            data="mp:music123:1",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=900),
            from_user=SimpleNamespace(id=77),
        )
        payload = {
            "user_id": 77,
            "query": "artist",
            "results": [
                {
                    "url": f"https://www.youtube.com/watch?v={index}",
                    "display_title": f"Artist - Track {index}",
                    "button_label": f"Artist - Track {index}",
                    "duration_label": "3:00",
                }
                for index in range(7)
            ],
        }

        with mock.patch(
            "bot.handlers.callback_registry.resolve_music_search",
            return_value=payload,
        ):
            coordinator._handle_music_page_callback(call)

        bot.edit_message_text.assert_called_once()

    def test_music_selection_callback_submits_youtube_audio_download(self):
        bot = mock.Mock()
        bot.send_message.return_value = SimpleNamespace(message_id=903, chat=SimpleNamespace(id=55))
        coordinator = BotHandlerCoordinator(bot)
        call = SimpleNamespace(
            id="cb-music-select",
            data="ms:music123:1",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=901),
            from_user=SimpleNamespace(id=77),
        )
        payload = {
            "user_id": 77,
            "query": "artist",
            "results": [
                {"url": "https://www.youtube.com/watch?v=one"},
                {"url": "https://www.youtube.com/watch?v=two"},
            ],
        }

        with mock.patch(
            "bot.handlers.callback_registry.resolve_music_search",
            return_value=payload,
        ), mock.patch.object(
            coordinator,
            "_submit_background_task",
            return_value=object(),
        ) as submit_task:
            coordinator._handle_music_selection_callback(call)

        submit_task.assert_called_once_with(
            "music_audio_download",
            mock.ANY,
            bot,
            55,
            "https://www.youtube.com/watch?v=two",
            903,
            mock.ANY,
        )

    def test_music_selection_callback_rejects_other_user(self):
        bot = mock.Mock()
        coordinator = BotHandlerCoordinator(bot)
        call = SimpleNamespace(
            id="cb-music-foreign",
            data="ms:music123:0",
            message=SimpleNamespace(chat=SimpleNamespace(id=55), message_id=901),
            from_user=SimpleNamespace(id=88),
        )

        with mock.patch(
            "bot.handlers.callback_registry.resolve_music_search",
            return_value={"user_id": 77, "query": "artist", "results": [{"url": "https://youtu.be/test"}]},
        ):
            coordinator._handle_music_selection_callback(call)

        bot.answer_callback_query.assert_called_once_with("cb-music-foreign", text=mock.ANY)


if __name__ == "__main__":
    unittest.main()
