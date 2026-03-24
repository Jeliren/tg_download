import unittest

from services.platforms import INSTAGRAM, YOUTUBE, detect_platform


class PlatformDetectionTests(unittest.TestCase):
    def test_detects_youtube_watch_url(self):
        self.assertEqual(
            detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            YOUTUBE,
        )

    def test_detects_youtube_short_url(self):
        self.assertEqual(detect_platform("youtu.be/dQw4w9WgXcQ"), YOUTUBE)

    def test_detects_instagram_reel(self):
        self.assertEqual(
            detect_platform("https://www.instagram.com/reel/ABC123/"),
            INSTAGRAM,
        )

    def test_rejects_instagram_profile_url(self):
        self.assertIsNone(detect_platform("https://www.instagram.com/some_profile/"))


if __name__ == "__main__":
    unittest.main()
