import unittest

from utils.logging_utils import _sanitize_text


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


if __name__ == "__main__":
    unittest.main()
