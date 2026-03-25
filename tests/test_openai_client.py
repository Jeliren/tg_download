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
        ):
            response = openai_client.post_openai_json(
                "responses",
                {"input": "hello"},
                api_key="test-key",
            )

        self.assertIs(response, second_response)
        self.assertEqual(post_mock.call_count, 2)
        sleep_mock.assert_called_once_with(1)

    def test_post_openai_multipart_raises_temporary_error_after_connection_failures(self):
        with (
            mock.patch(
                "services.openai_client.requests.post",
                side_effect=requests.ConnectionError("network down"),
            ) as post_mock,
            mock.patch("services.openai_client.time.sleep") as sleep_mock,
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


if __name__ == "__main__":
    unittest.main()
