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


if __name__ == "__main__":
    unittest.main()
