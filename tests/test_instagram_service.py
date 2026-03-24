import unittest
from unittest import mock

from services import instagram_service


class InstagramServiceHelpersTests(unittest.TestCase):
    def test_classifies_auth_required_errors(self):
        error = RuntimeError(
            "Login required. Use --cookies for the authentication."
        )

        self.assertEqual(instagram_service._classify_instagram_error(error), "auth_required")

    def test_classifies_rate_limited_errors(self):
        error = RuntimeError(
            "Requested content is not available, rate-limit reached. Please wait a few minutes."
        )

        self.assertEqual(instagram_service._classify_instagram_error(error), "rate_limited")

    def test_classifies_audience_restricted_errors(self):
        error = RuntimeError(
            "This content may be inappropriate: It's unavailable for certain audiences."
        )

        self.assertEqual(instagram_service._classify_instagram_error(error), "audience_restricted")

    def test_prefers_mp4_h264_for_instagram_video_downloads(self):
        options = instagram_service._build_yt_dlp_options("video", temp_dir="/tmp/ig-test", download=True)

        self.assertEqual(options["merge_output_format"], "mp4")
        self.assertIn("bestvideo[ext=mp4][vcodec*=avc1]", options["format"])
        self.assertEqual(options["outtmpl"], "/tmp/ig-test/instagram_video.%(ext)s")

    def test_auth_options_use_no_auth_first_and_optional_cookiefile(self):
        with mock.patch.object(instagram_service, "INSTAGRAM_COOKIES_FILE", "/tmp/ig-cookies.txt"), \
             mock.patch("services.instagram_service.os.path.exists", return_value=True):
            options = list(instagram_service._iter_yt_dlp_auth_options())

        self.assertEqual(options[0], ("no-auth", {}))
        self.assertIn(
            (
                "cookiefile:/tmp/ig-cookies.txt",
                {"cookiefile": "/tmp/ig-cookies.txt"},
            ),
            options,
        )

    def test_auth_options_do_not_use_browser_cookies(self):
        with mock.patch.object(instagram_service, "INSTAGRAM_COOKIES_FILE", ""):
            options = list(instagram_service._iter_yt_dlp_auth_options())

        flattened = [item for _, option in options for item in option.keys()]
        self.assertNotIn("cookiesfrombrowser", flattened)

    def test_detects_normalization_need_for_non_telegram_video(self):
        profile = {
            "format_name": "matroska,webm",
            "video_codec": "vp9",
            "audio_codec": "opus",
            "pix_fmt": "yuv444p",
            "width": 720,
            "height": 1280,
        }

        self.assertTrue(instagram_service._video_needs_telegram_normalization(profile))

    def test_skips_normalization_for_safe_mp4_profile(self):
        profile = {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "video_codec": "h264",
            "audio_codec": "aac",
            "pix_fmt": "yuv420p",
            "width": 720,
            "height": 1280,
        }

        self.assertFalse(instagram_service._video_needs_telegram_normalization(profile))

    def test_soft_availability_check_for_supported_instagram_url_with_query(self):
        self.assertTrue(
            instagram_service.check_instagram_availability(
                "https://www.instagram.com/reel/ABC123/?igsh=MTIz"
            )
        )

    def test_builds_description_message_from_info(self):
        text = instagram_service._build_instagram_description_message(
            "https://www.instagram.com/reel/ABC123/?igsh=123",
            {"description": "Тестовое описание"},
        )

        self.assertIn("Тестовое описание", text)
        self.assertIn("https://www.instagram.com/reel/ABC123/", text)

    def test_builds_description_message_from_html_fallback(self):
        with mock.patch.object(
            instagram_service,
            "_fetch_instagram_description_from_page",
            return_value="Описание из meta",
        ):
            text = instagram_service._build_instagram_description_message(
                "https://www.instagram.com/reel/ABC123/?igsh=123",
                None,
            )

        self.assertIn("Описание из meta", text)

    def test_builds_honest_user_message_for_auth_required(self):
        text = instagram_service._build_instagram_user_message("auth_required")

        self.assertIn("публичном режиме", text)
        self.assertIn("Instagram", text)

    def test_does_not_retry_rate_limited_errors(self):
        self.assertFalse(instagram_service._is_retryable_instagram_error("rate_limited"))

    def test_maps_account_challenge_reason(self):
        self.assertEqual(
            instagram_service._map_account_reason("challenge_required"),
            "account_challenge_required",
        )

    def test_extract_info_with_account_skips_unsupported_story_urls(self):
        with mock.patch.object(instagram_service, "instagram_account_is_configured", return_value=True), \
             mock.patch.object(instagram_service, "instagram_account_supports_url", return_value=False), \
             mock.patch.object(instagram_service, "get_media_via_account") as get_media:
            result = instagram_service._extract_info_with_account(
                "https://www.instagram.com/stories/testuser/1234567890/"
            )

        self.assertIsNone(result)
        get_media.assert_not_called()


class InstagramServiceRuntimeTests(unittest.TestCase):
    def test_video_download_surfaces_best_effort_unavailable_reason(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with mock.patch.object(
            instagram_service,
            "start_progress_message",
            return_value=stop_event,
        ), mock.patch.object(
            instagram_service,
            "_download_instagram_video_asset",
            side_effect=instagram_service.InstagramUnavailableError("rate_limited", "429"),
        ):
            instagram_service.download_instagram_video(
                bot,
                chat_id=42,
                url="https://www.instagram.com/reel/ABC123/?igsh=123",
                message_id=100,
            )

        bot.edit_message_text.assert_any_call(
            mock.ANY,
            chat_id=42,
            message_id=100,
        )
        self.assertTrue(
            any(
                "временно ограничил доступ" in call.args[1]
                for call in bot.send_message.call_args_list
            )
        )
        stop_event.set.assert_called_once()

    def test_description_download_surfaces_unavailable_reason_instead_of_false_missing_description(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with mock.patch.object(
            instagram_service,
            "start_progress_message",
            return_value=stop_event,
        ), mock.patch.object(
            instagram_service,
            "_extract_info_with_account",
            side_effect=instagram_service.InstagramUnavailableError("auth_required", "login required"),
        ), mock.patch.object(
            instagram_service,
            "_extract_info_with_yt_dlp",
            side_effect=instagram_service.InstagramUnavailableError("auth_required", "login required"),
        ), mock.patch.object(
            instagram_service,
            "_build_instagram_description_message",
            return_value=None,
        ):
            instagram_service.download_instagram_description(
                bot,
                chat_id=42,
                url="https://www.instagram.com/reel/ABC123/?igsh=123",
                message_id=100,
            )

        self.assertTrue(
            any(
                "публичном режиме" in call.args[1]
                for call in bot.send_message.call_args_list
                if len(call.args) > 1
            )
        )
        stop_event.set.assert_called_once()

    def test_description_download_reports_missing_only_when_description_is_actually_missing(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with mock.patch.object(
            instagram_service,
            "start_progress_message",
            return_value=stop_event,
        ), mock.patch.object(
            instagram_service,
            "_extract_info_with_account",
            return_value=None,
        ), mock.patch.object(
            instagram_service,
            "_extract_info_with_yt_dlp",
            return_value=None,
        ), mock.patch.object(
            instagram_service,
            "_build_instagram_description_message",
            return_value=None,
        ):
            instagram_service.download_instagram_description(
                bot,
                chat_id=42,
                url="https://www.instagram.com/reel/ABC123/?igsh=123",
                message_id=100,
            )

        self.assertTrue(
            any(
                "Не удалось найти описание" in call.args[1]
                for call in bot.send_message.call_args_list
                if len(call.args) > 1
            )
        )
        stop_event.set.assert_called_once()

    def test_transcribe_instagram_reel_sends_transcript_text(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with mock.patch.object(
            instagram_service,
            "OPENAI_API_KEY",
            "test-key",
        ), mock.patch.object(
            instagram_service,
            "start_progress_message",
            return_value=stop_event,
        ), mock.patch.object(
            instagram_service,
            "_download_instagram_audio_asset",
            return_value=("/tmp/ig-transcript", "/tmp/ig-transcript/audio.mp3", {}),
        ), mock.patch(
            "services.instagram_service.os.path.getsize",
            return_value=1024,
        ), mock.patch.object(
            instagram_service,
            "transcribe_audio_with_openai",
            return_value="текст рилса",
        ), mock.patch.object(
            instagram_service,
            "send_text_chunks",
        ) as send_text_chunks:
            instagram_service.transcribe_instagram_reel(
                bot,
                chat_id=42,
                url="https://www.instagram.com/reel/ABC123/?igsh=123",
                message_id=100,
            )

        send_text_chunks.assert_called_once_with(bot, 42, "текст рилса")
        self.assertTrue(
            any(
                call.args == (42, instagram_service.READY_FOR_MORE_TEXT)
                for call in bot.send_message.call_args_list
            )
        )
        stop_event.set.assert_called_once()

    def test_transcribe_instagram_reel_reports_empty_transcript_honestly(self):
        bot = mock.Mock()
        stop_event = mock.Mock()

        with mock.patch.object(
            instagram_service,
            "OPENAI_API_KEY",
            "test-key",
        ), mock.patch.object(
            instagram_service,
            "start_progress_message",
            return_value=stop_event,
        ), mock.patch.object(
            instagram_service,
            "_download_instagram_audio_asset",
            return_value=("/tmp/ig-transcript", "/tmp/ig-transcript/audio.mp3", {}),
        ), mock.patch(
            "services.instagram_service.os.path.getsize",
            return_value=1024,
        ), mock.patch.object(
            instagram_service,
            "transcribe_audio_with_openai",
            return_value="",
        ):
            instagram_service.transcribe_instagram_reel(
                bot,
                chat_id=42,
                url="https://www.instagram.com/reel/ABC123/?igsh=123",
                message_id=100,
            )

        bot.edit_message_text.assert_any_call(
            "⚠️ В рилсе не удалось распознать речь.",
            chat_id=42,
            message_id=100,
        )
        self.assertTrue(
            any(
                "не нашёл распознаваемой речи" in call.args[1]
                for call in bot.send_message.call_args_list
                if len(call.args) > 1
            )
        )
        stop_event.set.assert_called_once()


if __name__ == "__main__":
    unittest.main()
