import unittest

from bot.keyboards import (
    create_format_selection_markup,
    create_inline_markup,
    create_main_reply_markup,
    create_music_results_markup,
    create_transcription_confirmation_markup,
    create_uploaded_audio_markup,
    create_uploaded_video_markup,
    create_uploaded_voice_markup,
)


class KeyboardTests(unittest.TestCase):
    def test_main_reply_markup_contains_music_and_help_buttons(self):
        markup = create_main_reply_markup()

        labels = [button["text"] for row in markup.keyboard for button in row]

        self.assertIn("Музыка", labels)
        self.assertIn("/help", labels)

    def test_instagram_markup_can_include_description_button(self):
        markup = create_inline_markup("abcd1234", include_description=True, include_transcription=True)

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertIn("v:abcd1234", callback_data)
        self.assertIn("a:abcd1234", callback_data)
        self.assertIn("d:abcd1234", callback_data)
        self.assertIn("tr:abcd1234", callback_data)

    def test_default_markup_does_not_include_description_button(self):
        markup = create_inline_markup("abcd1234")

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertNotIn("d:abcd1234", callback_data)
        self.assertNotIn("s:abcd1234", callback_data)
        self.assertNotIn("tr:abcd1234", callback_data)

    def test_youtube_markup_can_include_summary_button(self):
        markup = create_inline_markup("abcd1234", include_summary=True)

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertIn("v:abcd1234", callback_data)
        self.assertIn("a:abcd1234", callback_data)
        self.assertIn("s:abcd1234", callback_data)

    def test_transcription_confirmation_markup_has_confirm_and_cancel(self):
        markup = create_transcription_confirmation_markup("abcd1234")

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertIn("t:abcd1234", callback_data)
        self.assertIn("x:abcd1234", callback_data)

    def test_uploaded_video_markup_has_circle_transcript_and_summary(self):
        markup = create_uploaded_video_markup("vid1234567")

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertIn("vn:vid1234567", callback_data)
        self.assertIn("vt:vid1234567", callback_data)
        self.assertIn("vs:vid1234567", callback_data)

    def test_uploaded_audio_markup_has_voice_transcript_and_summary(self):
        markup = create_uploaded_audio_markup("aud1234567")

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertIn("an:aud1234567", callback_data)
        self.assertIn("at:aud1234567", callback_data)
        self.assertIn("as:aud1234567", callback_data)

    def test_uploaded_voice_markup_has_only_transcript_and_summary(self):
        markup = create_uploaded_voice_markup("voc1234567")

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertNotIn("an:voc1234567", callback_data)
        self.assertIn("at:voc1234567", callback_data)
        self.assertIn("as:voc1234567", callback_data)

    def test_music_results_markup_has_track_buttons_and_pagination(self):
        markup = create_music_results_markup(
            "music123",
            [
                {"button_label": "Artist - Track 1"},
                {"button_label": "Artist - Track 2"},
            ],
            page=0,
            total_pages=2,
        )

        callback_data = [button.callback_data for row in markup.keyboard for button in row]

        self.assertIn("ms:music123:0", callback_data)
        self.assertIn("ms:music123:1", callback_data)
        self.assertIn("mp:music123:1", callback_data)

    def test_format_selection_markup_uses_prebuilt_short_callback_ids(self):
        markup = create_format_selection_markup(
            [
                {
                    "format_id": "bv*[height<=?1080]+ba/b[height<=?1080]",
                    "format_name": "1080p Full HD",
                    "height": 1080,
                    "filesize": 15 * 1024 * 1024,
                    "callback_data": "f:fmt1234567",
                },
                {
                    "format_id": "bv*[height<=?720]+ba/b[height<=?720]",
                    "format_name": "720p HD",
                    "height": 720,
                    "filesize_approx": 9 * 1024 * 1024,
                    "callback_data": "f:fmt7654321",
                },
            ],
            best_callback_data="f:fmtbest000",
        )

        buttons = [
            button
            for row in markup.keyboard
            for button in row
        ]
        callback_data = [button.callback_data for button in buttons]
        labels = [button.text for button in buttons]

        self.assertIn("f:fmt1234567", callback_data)
        self.assertIn("f:fmt7654321", callback_data)
        self.assertIn("f:fmtbest000", callback_data)
        self.assertTrue(all(len(item.encode("utf-8")) <= 64 for item in callback_data))
        self.assertIn("1080p Full HD ~15.0 MB", labels)
        self.assertIn("720p HD ~9.0 MB", labels)

    def test_format_selection_markup_can_omit_best_button(self):
        markup = create_format_selection_markup(
            [
                {
                    "format_id": "bv*[height<=?480]+ba/b[height<=?480]",
                    "format_name": "480p SD",
                    "height": 480,
                    "callback_data": "f:fmt4800000",
                }
            ],
            best_callback_data=None,
        )

        callback_data = [
            button.callback_data
            for row in markup.keyboard
            for button in row
        ]

        self.assertEqual(callback_data, ["f:fmt4800000"])


if __name__ == "__main__":
    unittest.main()
