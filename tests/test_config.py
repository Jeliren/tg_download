import os
import tempfile
import unittest
from unittest.mock import patch

import config


class ConfigValidationTests(unittest.TestCase):
    def test_validate_config_raises_without_token(self):
        with patch.object(config, "BOT_TOKEN", ""):
            with self.assertRaises(RuntimeError):
                config.validate_config()

    def test_validate_config_accepts_token_like_value(self):
        with patch.object(config, "BOT_TOKEN", "123456:valid_token_value"):
            config.validate_config()

    def test_runtime_warnings_include_partial_instagram_account_credentials(self):
        with patch.object(config, "INSTAGRAM_USERNAME", "user"), \
             patch.object(config, "INSTAGRAM_PASSWORD", ""):
            warnings = config.get_runtime_warnings()

        self.assertEqual(len(warnings), 1)
        self.assertIn("INSTAGRAM_USERNAME", warnings[0])
        self.assertIn("INSTAGRAM_PASSWORD", warnings[0])

    def test_load_dotenv_supports_export_prefix(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as dotenv_file:
            dotenv_file.write("export STAGE1_DOTENV_TEST=value\n")
            dotenv_path = dotenv_file.name

        self.addCleanup(lambda: os.path.exists(dotenv_path) and os.remove(dotenv_path))

        with patch.dict(os.environ, {}, clear=True):
            config._load_dotenv(dotenv_path)
            self.assertEqual(os.getenv("STAGE1_DOTENV_TEST"), "value")

    def test_runtime_warnings_include_partial_telegram_proxy_config(self):
        with patch.object(config, "TELEGRAM_PROXY_SCHEME", "socks5"), \
             patch.object(config, "TELEGRAM_PROXY_HOST", "127.0.0.1"), \
             patch.object(config, "TELEGRAM_PROXY_PORT", 0), \
             patch.object(config, "TELEGRAM_PROXY_USERNAME", ""), \
             patch.object(config, "TELEGRAM_PROXY_PASSWORD", ""):
            warnings = config.get_runtime_warnings()

        self.assertEqual(len(warnings), 1)
        self.assertIn("TELEGRAM_PROXY_PORT", warnings[0])

    def test_get_telegram_proxy_url_uses_credentials_when_proxy_is_configured(self):
        with patch.object(config, "TELEGRAM_PROXY_SCHEME", "socks5"), \
             patch.object(config, "TELEGRAM_PROXY_HOST", "10.0.0.1"), \
             patch.object(config, "TELEGRAM_PROXY_PORT", 1080), \
             patch.object(config, "TELEGRAM_PROXY_USERNAME", "user"), \
             patch.object(config, "TELEGRAM_PROXY_PASSWORD", "pass"):
            self.assertEqual(
                config.get_telegram_proxy_url(),
                "socks5://user:pass@10.0.0.1:1080",
            )

    def test_get_outbound_proxy_url_falls_back_to_telegram_proxy(self):
        with patch.object(config, "OUTBOUND_PROXY_SCHEME", ""), \
             patch.object(config, "OUTBOUND_PROXY_HOST", ""), \
             patch.object(config, "OUTBOUND_PROXY_PORT", 0), \
             patch.object(config, "OUTBOUND_PROXY_USERNAME", ""), \
             patch.object(config, "OUTBOUND_PROXY_PASSWORD", ""), \
             patch.object(config, "TELEGRAM_PROXY_SCHEME", "socks5"), \
             patch.object(config, "TELEGRAM_PROXY_HOST", "10.0.0.2"), \
             patch.object(config, "TELEGRAM_PROXY_PORT", 2080), \
             patch.object(config, "TELEGRAM_PROXY_USERNAME", "user"), \
             patch.object(config, "TELEGRAM_PROXY_PASSWORD", "pass"):
            self.assertEqual(
                config.get_outbound_proxy_url(),
                "socks5://user:pass@10.0.0.2:2080",
            )


if __name__ == "__main__":
    unittest.main()
