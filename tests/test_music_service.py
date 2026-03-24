import unittest
from unittest import mock

from services import music_service


class MusicServiceTests(unittest.TestCase):
    def test_search_music_normalizes_and_prefers_more_music_like_results(self):
        ydl_instance = mock.MagicMock()
        ydl_instance.__enter__.return_value.extract_info.return_value = {
            "entries": [
                {
                    "id": "podcast12345",
                    "title": "Artist interview podcast episode",
                    "uploader": "Some Channel",
                    "duration": 1200,
                },
                {
                    "id": "music12345",
                    "title": "Artist - Track (Official Audio)",
                    "uploader": "Artist - Topic",
                    "duration": 215,
                },
            ]
        }

        with mock.patch("services.music_service.yt_dlp.YoutubeDL", return_value=ydl_instance):
            results = music_service.search_music("artist track")

        self.assertEqual(results[0]["display_title"], "Artist - Track (Official Audio)")
        self.assertEqual(results[0]["url"], "https://www.youtube.com/watch?v=music12345")
        self.assertEqual(results[0]["duration_label"], "3:35")

    def test_search_music_uses_artist_and_track_metadata_when_available(self):
        ydl_instance = mock.MagicMock()
        ydl_instance.__enter__.return_value.extract_info.return_value = {
            "entries": [
                {
                    "id": "music12345",
                    "title": "Some long title",
                    "artist": "Daft Punk",
                    "track": "One More Time",
                    "duration": 320,
                }
            ]
        }

        with mock.patch("services.music_service.yt_dlp.YoutubeDL", return_value=ydl_instance):
            results = music_service.search_music("daft punk")

        self.assertEqual(results[0]["display_title"], "Daft Punk - One More Time")
        self.assertEqual(results[0]["button_label"], "Daft Punk - One More Time")

    def test_search_music_wraps_runtime_errors(self):
        ydl_instance = mock.MagicMock()
        ydl_instance.__enter__.return_value.extract_info.side_effect = RuntimeError("temporary failure")

        with mock.patch("services.music_service.yt_dlp.YoutubeDL", return_value=ydl_instance):
            with self.assertRaises(music_service.MusicSearchError):
                music_service.search_music("artist")


if __name__ == "__main__":
    unittest.main()
