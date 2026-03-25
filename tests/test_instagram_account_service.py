import unittest
from types import SimpleNamespace
from unittest import mock

from instagrapi.exceptions import BadPassword, ChallengeRequired, PleaseWaitFewMinutes

from services import instagram_account_service


class InstagramAccountServiceTests(unittest.TestCase):
    def test_classifies_bad_password(self):
        self.assertEqual(
            instagram_account_service._classify_account_exception(BadPassword("bad password")),
            "bad_credentials",
        )

    def test_classifies_challenge(self):
        self.assertEqual(
            instagram_account_service._classify_account_exception(ChallengeRequired("challenge")),
            "challenge_required",
        )

    def test_classifies_rate_limit(self):
        self.assertEqual(
            instagram_account_service._classify_account_exception(PleaseWaitFewMinutes("wait")),
            "rate_limited",
        )

    def test_get_media_requires_configured_account(self):
        with mock.patch.object(instagram_account_service, "INSTAGRAM_USERNAME", ""), \
             mock.patch.object(instagram_account_service, "INSTAGRAM_PASSWORD", ""):
            with self.assertRaises(instagram_account_service.InstagramAccountError):
                instagram_account_service.get_media_via_account("https://www.instagram.com/reel/ABC123/")

    def test_extract_media_payload_uses_shortcode_private_path(self):
        client = mock.Mock()
        media = mock.Mock()
        media.caption_text = "caption"
        media.title = "title"
        media.video_url = "https://cdn.example/video.mp4"
        media.user = mock.Mock(username="author")
        media.product_type = "clips"
        media.resources = []
        client.media_pk_from_code.return_value = "12345"
        client.media_info_v1.return_value = media

        payload = instagram_account_service._extract_media_payload(
            client,
            "https://www.instagram.com/reel/ABC123/?igsh=1",
        )

        client.media_pk_from_code.assert_called_once_with("ABC123")
        client.media_info_v1.assert_called_once_with("12345")
        self.assertEqual(payload.video_url, "https://cdn.example/video.mp4")

    def test_get_media_uses_cache_for_repeated_shortcode(self):
        payload = instagram_account_service.InstagramAccountMedia(
            media_pk="123",
            caption_text="caption",
            title="title",
            video_url="https://cdn.example/video.mp4",
            username="author",
            product_type="clips",
        )

        instagram_account_service._MEDIA_CACHE = instagram_account_service.ExpiringStore(ttl=60)
        with mock.patch.object(
            instagram_account_service,
            "_run_with_client",
            return_value=payload,
        ) as run_mock, mock.patch.object(
            instagram_account_service,
            "INSTAGRAM_USERNAME",
            "user",
        ), mock.patch.object(
            instagram_account_service,
            "INSTAGRAM_PASSWORD",
            "pass",
        ):
            first = instagram_account_service.get_media_via_account(
                "https://www.instagram.com/reel/ABC123/?igsh=1"
            )
            second = instagram_account_service.get_media_via_account(
                "https://www.instagram.com/reel/ABC123/?igsh=2"
            )

        self.assertIs(first, payload)
        self.assertIs(second, payload)
        run_mock.assert_called_once()

    def test_account_mode_supports_shortcode_urls_but_not_story_urls(self):
        self.assertTrue(
            instagram_account_service.instagram_account_supports_url(
                "https://www.instagram.com/reel/ABC123/?igsh=1"
            )
        )
        self.assertFalse(
            instagram_account_service.instagram_account_supports_url(
                "https://www.instagram.com/stories/testuser/1234567890/"
            )
        )

    def test_get_media_rejects_unsupported_story_url_for_account_mode(self):
        with mock.patch.object(instagram_account_service, "INSTAGRAM_USERNAME", "user"), \
             mock.patch.object(instagram_account_service, "INSTAGRAM_PASSWORD", "pass"):
            with self.assertRaises(instagram_account_service.InstagramAccountError) as error_ctx:
                instagram_account_service.get_media_via_account(
                    "https://www.instagram.com/stories/testuser/1234567890/"
                )

        self.assertEqual(error_ctx.exception.reason, "unsupported_url")

    def test_build_client_uses_external_timeouts_instead_of_one_second_default(self):
        fake_client = SimpleNamespace(
            private=SimpleNamespace(request=lambda *args, **kwargs: None, proxies={}),
            public=SimpleNamespace(request=lambda *args, **kwargs: None, proxies={}),
            set_proxy=mock.Mock(),
        )

        with mock.patch.object(instagram_account_service, "Client", return_value=fake_client), \
             mock.patch.object(
                 instagram_account_service,
                 "get_outbound_proxy_url",
                 return_value="socks5://127.0.0.1:1080",
             ), \
             mock.patch.object(
                 instagram_account_service,
                 "get_outbound_requests_proxies",
                 return_value={"http": "socks5://127.0.0.1:1080", "https": "socks5://127.0.0.1:1080"},
             ):
            client = instagram_account_service._build_client()

        self.assertEqual(
            client.request_timeout,
            instagram_account_service.EXTERNAL_CONNECT_TIMEOUT + instagram_account_service.EXTERNAL_READ_TIMEOUT,
        )
        fake_client.set_proxy.assert_called_once_with("socks5://127.0.0.1:1080")
        self.assertEqual(fake_client.private.proxies["https"], "socks5://127.0.0.1:1080")


if __name__ == "__main__":
    unittest.main()
