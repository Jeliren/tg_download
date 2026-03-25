import unittest
from unittest import mock

import requests

from services import openai_client


class OpenAIClientTests(unittest.TestCase):
    def test_post_openai_json_retries_retryable_status(self):
        first_response = mock.Mock(ok=False, status_code=429, text="rate limited")
        second_response = mock.Mock(ok=True, status_code=200)

        with (
            mock.patch(
                "services.openai_client.requests.post", side_effect=[first_response, second_response]
            ) as post_mock,
            mock.patch("services.openai_client.time.sleep") as sleep_mock,
            mock.patch(
                "services.openai_client.get_outbound_requests_proxies",
                return_value={"http": "socks5://127.0.0.1:1080", "https": "socks5://127.0.0.1:1080"},
            ),
        ):
            response = openai_client.post_openai_json(
                "responses",
                {"input": "hello"},
                api_key="test-key",
            )

        self.assertIs(response, second_response)
        self.assertEqual(post_mock.call_count, 2)
        sleep_mock.assert_called_once_with(1)
        self.assertEqual(
            post_mock.call_args.kwargs["proxies"],
            {"http": "socks5://127.0.0.1:1080", "https": "socks5://127.0.0.1:1080"},
        )

    def test_post_openai_multipart_raises_temporary_error_after_connection_failures(self):
        with (
            mock.patch(
                "services.openai_client.requests.post",
                side_effect=requests.ConnectionError("network down"),
            ) as post_mock,
            mock.patch("services.openai_client.time.sleep") as sleep_mock,
            mock.patch(
                "services.openai_client.get_outbound_requests_proxies",
                return_value={"http": "socks5://127.0.0.1:1080", "https": "socks5://127.0.0.1:1080"},
            ),
        ):
            with self.assertRaises(openai_client.OpenAITemporaryError):
                openai_client.post_openai_multipart(
                    "audio/transcriptions",
                    api_key="test-key",
                    data={"model": "gpt-test"},
                    files={"file": ("clip.mp3", object())},
                )

        self.assertEqual(post_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_post_openai_json_uses_outbound_proxy_when_configured(self):
        response = mock.Mock(ok=True, status_code=200)

        with (
            mock.patch("services.openai_client.requests.post", return_value=response) as post_mock,
            mock.patch(
                "services.openai_client.get_outbound_requests_proxies",
                return_value={"http": "socks5://127.0.0.1:1080", "https": "socks5://127.0.0.1:1080"},
            ),
        ):
            openai_client.post_openai_json(
                "responses",
                {"input": "hello"},
                api_key="test-key",
            )

        self.assertEqual(
            post_mock.call_args.kwargs["proxies"],
            {"http": "socks5://127.0.0.1:1080", "https": "socks5://127.0.0.1:1080"},
        )


if __name__ == "__main__":
    unittest.main()
