import unittest
from unittest import mock

from utils.logging_utils import _sanitize_text, perf_monitor


class LoggingSanitizerTests(unittest.TestCase):
    def test_redacts_telegram_bot_token_patterns(self):
        original = (
            "https://api.telegram.org/bot12345678:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef/getUpdates "
            "12345678:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef"
        )

        sanitized = _sanitize_text(original)

        self.assertNotIn("12345678:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", sanitized)
        self.assertIn("bot<redacted-bot-token>", sanitized)
        self.assertIn("<redacted-bot-token>", sanitized)


class PerfMonitorTests(unittest.TestCase):
    def test_marks_false_result_as_failed(self):
        @perf_monitor
        def download_media():
            return False

        with mock.patch("utils.logging_utils.log_perf") as log_perf:
            self.assertFalse(download_media())

        self.assertIn("DOWNLOAD|download_media|FAILED|", log_perf.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
