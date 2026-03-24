import unittest

from bot.callback_router import (
    CALLBACK_ROUTE_DOWNLOAD,
    CALLBACK_ROUTE_FORMAT,
    CALLBACK_ROUTE_MUSIC,
    CALLBACK_ROUTE_UNKNOWN,
    CALLBACK_ROUTE_UPLOADED_AUDIO,
    CALLBACK_ROUTE_UPLOADED_VIDEO,
    classify_callback_data,
)


class CallbackRouterTests(unittest.TestCase):
    def test_classifies_download_callback(self):
        route = classify_callback_data("v:url123")

        self.assertEqual(route.kind, CALLBACK_ROUTE_DOWNLOAD)
        self.assertEqual(route.action, "v")

    def test_classifies_uploaded_video_callback(self):
        route = classify_callback_data("vs:vid1234567")

        self.assertEqual(route.kind, CALLBACK_ROUTE_UPLOADED_VIDEO)
        self.assertEqual(route.action, "vs")

    def test_classifies_uploaded_audio_callback(self):
        route = classify_callback_data("as:aud1234567")

        self.assertEqual(route.kind, CALLBACK_ROUTE_UPLOADED_AUDIO)
        self.assertEqual(route.action, "as")

    def test_classifies_format_callback(self):
        route = classify_callback_data("f:fmt1234567")

        self.assertEqual(route.kind, CALLBACK_ROUTE_FORMAT)
        self.assertEqual(route.action, "f")

    def test_classifies_music_callback(self):
        route = classify_callback_data("ms:music123:4")

        self.assertEqual(route.kind, CALLBACK_ROUTE_MUSIC)
        self.assertEqual(route.action, "ms")

    def test_classifies_unknown_callback(self):
        route = classify_callback_data("zzz:something")

        self.assertEqual(route.kind, CALLBACK_ROUTE_UNKNOWN)

    def test_classifies_empty_callback_as_unknown(self):
        route = classify_callback_data("")

        self.assertEqual(route.kind, CALLBACK_ROUTE_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
