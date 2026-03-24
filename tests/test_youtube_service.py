import unittest
from unittest import mock

from services import youtube_service


class YouTubeServiceHelpersTests(unittest.TestCase):
    def test_parse_vtt_transcript_skips_headers_and_only_deduplicates_consecutive_lines(self):
        transcript = youtube_service._parse_vtt_transcript(
            "\n".join(
                [
                    "WEBVTT",
                    "Kind: captions",
                    "Language: en",
                    "",
                    "cue-1",
                    "00:00:00.000 --> 00:00:02.000",
                    "<c>hello</c>",
                    "",
                    "00:00:02.000 --> 00:00:04.000",
                    "hello",
                    "",
                    "00:00:04.000 --> 00:00:06.000",
                    "world",
                    "",
                    "00:00:06.000 --> 00:00:08.000",
                    "hello",
                ]
            )
        )

        self.assertEqual(transcript, "hello\nworld\nhello")

    def test_split_text_chunks_splits_single_long_line(self):
        chunks = youtube_service._split_text_chunks("x" * 50000, chunk_size=40000)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 40000)
        self.assertEqual(len(chunks[1]), 10000)

    def test_pick_subtitle_language_prefers_ru_then_en(self):
        language, source = youtube_service._pick_subtitle_language(
            {
                "subtitles": {
                    "en": [{}],
                    "ru-RU": [{}],
                },
                "automatic_captions": {
                    "fr": [{}],
                },
            }
        )

        self.assertEqual(language, "ru-RU")
        self.assertEqual(source, "subtitles")

    def test_pick_subtitle_language_falls_back_to_any_available_language(self):
        language, source = youtube_service._pick_subtitle_language(
            {
                "subtitles": {},
                "automatic_captions": {
                    "es": [{}],
                    "de": [{}],
                },
            }
        )

        self.assertEqual(language, "de")
        self.assertEqual(source, "automatic_captions")

    def test_get_youtube_formats_uses_real_video_heights(self):
        info = {
            "title": "Test clip",
            "formats": [
                {"format_id": "251", "vcodec": "none", "height": None},
                {"format_id": "137", "vcodec": "avc1", "height": 1080, "filesize": 10},
                {"format_id": "399", "vcodec": "av01", "height": 1080, "filesize": 15},
                {"format_id": "136", "vcodec": "avc1", "height": 720, "filesize_approx": 9},
                {"format_id": "135", "vcodec": "avc1", "height": 480, "filesize_approx": 5},
            ],
        }

        ydl_instance = mock.MagicMock()
        ydl_instance.__enter__.return_value.extract_info.return_value = info

        with mock.patch("services.youtube_service.yt_dlp.YoutubeDL", return_value=ydl_instance):
            result = youtube_service.get_youtube_formats("https://youtu.be/test")

        self.assertEqual(result["title"], "Test clip")
        self.assertEqual(
            [item["height"] for item in result["formats"]],
            [1080, 720, 480],
        )
        self.assertEqual(
            result["formats"][0]["format_id"],
            "bv*[height<=?1080]+ba/b[height<=?1080]",
        )

    def test_build_download_candidates_for_best_uses_available_heights(self):
        with mock.patch.object(
            youtube_service,
            "_extract_format_options_from_info",
            return_value={
                "title": "Test clip",
                "formats": [
                    {"format_id": "bv*[height<=?1080]+ba/b[height<=?1080]"},
                    {"format_id": "bv*[height<=?720]+ba/b[height<=?720]"},
                ],
            },
        ), mock.patch.object(
            youtube_service,
            "_load_youtube_info",
            return_value={"title": "Test clip", "formats": []},
        ):
            candidates = youtube_service._build_download_candidates(
                "https://youtu.be/test",
                "best",
            )

        self.assertEqual(
            candidates,
            [
                "bv*[height<=?1080]+ba/b[height<=?1080]",
                "bv*[height<=?720]+ba/b[height<=?720]",
            ],
        )

    def test_build_download_candidates_keeps_explicit_format(self):
        self.assertEqual(
            youtube_service._build_download_candidates(
                "https://youtu.be/test",
                "bv*[height<=?720]+ba/b[height<=?720]",
            ),
            ["bv*[height<=?720]+ba/b[height<=?720]"],
        )

    def test_build_download_candidates_uses_all_available_heights_not_only_ui_top_six(self):
        info = {
            "title": "Test clip",
            "formats": [
                {"format_id": "1", "vcodec": "avc1", "height": 2160, "filesize": 10},
                {"format_id": "2", "vcodec": "avc1", "height": 1440, "filesize": 9},
                {"format_id": "3", "vcodec": "avc1", "height": 1080, "filesize": 8},
                {"format_id": "4", "vcodec": "avc1", "height": 720, "filesize": 7},
                {"format_id": "5", "vcodec": "avc1", "height": 480, "filesize": 6},
                {"format_id": "6", "vcodec": "avc1", "height": 360, "filesize": 5},
                {"format_id": "7", "vcodec": "avc1", "height": 240, "filesize": 4},
                {"format_id": "8", "vcodec": "avc1", "height": 144, "filesize": 3},
            ],
        }

        with mock.patch.object(youtube_service, "_load_youtube_info", return_value=info):
            ui_formats = youtube_service.get_youtube_formats("https://youtu.be/test")
            candidates = youtube_service._build_download_candidates(
                "https://youtu.be/test",
                "best",
            )

        self.assertEqual(len(ui_formats["formats"]), 6)
        self.assertEqual(
            candidates,
            [
                "bv*[height<=?2160]+ba/b[height<=?2160]",
                "bv*[height<=?1440]+ba/b[height<=?1440]",
                "bv*[height<=?1080]+ba/b[height<=?1080]",
                "bv*[height<=?720]+ba/b[height<=?720]",
                "bv*[height<=?480]+ba/b[height<=?480]",
                "bv*[height<=?360]+ba/b[height<=?360]",
                "bv*[height<=?240]+ba/b[height<=?240]",
                "bv*[height<=?144]+ba/b[height<=?144]",
            ],
        )


class YouTubeServiceRuntimeTests(unittest.TestCase):
    def test_download_youtube_video_reoffers_lower_quality_when_selected_quality_is_too_large(self):
        bot = mock.Mock()
        stop_event = mock.Mock()
        ydl_instance = mock.MagicMock()
        ydl_instance.__enter__.return_value.extract_info.return_value = {"title": "Test clip"}

        with (
            mock.patch.object(youtube_service, "start_progress_message", return_value=stop_event),
            mock.patch.object(youtube_service, "_create_temp_dir", return_value="/tmp/youtube_video"),
            mock.patch.object(youtube_service, "_cleanup_temp_dir"),
            mock.patch.object(
                youtube_service,
                "_build_download_candidates",
                return_value=["bv*[height<=?1080]+ba/b[height<=?1080]"],
            ),
            mock.patch.object(
                youtube_service,
                "get_youtube_formats",
                return_value={
                    "title": "Test clip",
                    "formats": [
                        {
                            "format_id": "bv*[height<=?1080]+ba/b[height<=?1080]",
                            "format_name": "1080p Full HD",
                            "height": 1080,
                        },
                        {
                            "format_id": "bv*[height<=?720]+ba/b[height<=?720]",
                            "format_name": "720p HD",
                            "height": 720,
                        },
                        {
                            "format_id": "bv*[height<=?480]+ba/b[height<=?480]",
                            "format_name": "480p SD",
                            "height": 480,
                        },
                    ],
                },
            ),
            mock.patch("services.youtube_service.yt_dlp.YoutubeDL", return_value=ydl_instance),
            mock.patch.object(youtube_service, "_find_downloaded_file", return_value="/tmp/youtube_video/video.mp4"),
            mock.patch("services.youtube_service.os.path.getsize", return_value=youtube_service.MAX_FILE_SIZE + 1),
        ):
            youtube_service.download_youtube_video(
                bot,
                chat_id=42,
                url="https://youtu.be/test",
                message_id=100,
                format_id="bv*[height<=?1080]+ba/b[height<=?1080]",
            )

        self.assertTrue(
            any(
                "Выбранное качество слишком большое для Telegram" in (call.args[0] if call.args else "")
                for call in bot.edit_message_text.call_args_list
            )
        )
        reply_markup = bot.edit_message_text.call_args_list[-1].kwargs["reply_markup"]
        callback_data = [
            button.callback_data
            for row in reply_markup.keyboard
            for button in row
        ]
        self.assertEqual(len(callback_data), 2)
        self.assertTrue(all(item.startswith("f:") for item in callback_data))
        stop_event.set.assert_called_once()

    def test_summarize_youtube_video_reports_temporary_openai_failure(self):
        bot = mock.Mock()
        stop_event = mock.Mock()
        info = {
            "title": "Test clip",
            "subtitles": {"en": [{}]},
            "automatic_captions": {},
        }

        with (
            mock.patch.object(youtube_service, "OPENAI_API_KEY", "test-key"),
            mock.patch.object(youtube_service, "start_progress_message", return_value=stop_event),
            mock.patch.object(youtube_service, "_load_youtube_info", return_value=info),
            mock.patch.object(
                youtube_service,
                "_download_youtube_subtitles",
                return_value={"text": "transcript text", "source": "subtitles", "language": "en"},
            ),
            mock.patch.object(youtube_service, "_count_summary_chunks", return_value=1),
            mock.patch.object(
                youtube_service,
                "_summarize_transcript_text",
                side_effect=youtube_service.OpenAITemporaryError("responses", "timeout"),
            ),
        ):
            youtube_service.summarize_youtube_video(
                bot,
                chat_id=42,
                url="https://youtu.be/test",
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


if __name__ == "__main__":
    unittest.main()
