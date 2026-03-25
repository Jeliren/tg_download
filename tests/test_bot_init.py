import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import bot


class BotInitializationTests(unittest.TestCase):
    def setUp(self):
        self.telebot_module = types.ModuleType("telebot")
        self.apihelper_module = types.ModuleType("telebot.apihelper")
        self.apihelper_module.ApiTelegramException = RuntimeError
        self.apihelper_module.proxy = None
        self.apihelper_module.CONNECT_TIMEOUT = None
        self.apihelper_module.READ_TIMEOUT = None

        self.bot_instance = MagicMock()
        self.telebot_module.TeleBot = MagicMock(return_value=self.bot_instance)
        self.telebot_module.apihelper = self.apihelper_module
        self.telebot_module.logging = types.SimpleNamespace(INFO="INFO")
        self.telebot_module.logger = MagicMock()

        self.handlers_module = types.ModuleType("bot.handlers")
        self.handlers_module.register_handlers = MagicMock()

        self.module_patcher = patch.dict(
            sys.modules,
            {
                "telebot": self.telebot_module,
                "telebot.apihelper": self.apihelper_module,
                "bot.handlers": self.handlers_module,
            },
        )
        self.module_patcher.start()
        self.addCleanup(self.module_patcher.stop)

    def test_create_bot_keeps_direct_connection_when_probe_succeeds(self):
        with patch("config.validate_config"), \
             patch("config.BOT_TOKEN", "123:token"), \
             patch("config.CONNECT_TIMEOUT", 3), \
             patch("config.READ_TIMEOUT", 5), \
             patch("services.converter_service.check_ffmpeg", return_value=True), \
             patch("config.is_proxy_enabled", return_value=False), \
             patch("bot.log"):
            created_bot = bot.create_bot()

        self.assertIs(created_bot, self.bot_instance)
        self.assertEqual(self.apihelper_module.proxy, {})
        self.telebot_module.TeleBot.assert_called_once_with("123:token")
        self.handlers_module.register_handlers.assert_called_once_with(self.bot_instance)

    def test_create_bot_switches_to_proxy_when_proxy_is_enabled(self):
        with patch("config.validate_config"), \
             patch("config.BOT_TOKEN", "123:token"), \
             patch("config.CONNECT_TIMEOUT", 3), \
             patch("config.READ_TIMEOUT", 5), \
             patch("config.TELEGRAM_PROXY_SCHEME", "socks5"), \
             patch("config.TELEGRAM_PROXY_HOST", "185.242.107.204"), \
             patch("config.TELEGRAM_PROXY_PORT", 52398), \
             patch("config.is_proxy_enabled", return_value=True), \
             patch("config.get_telegram_proxy_url", return_value="socks5://user:pass@185.242.107.204:52398"), \
             patch("services.converter_service.check_ffmpeg", return_value=True), \
             patch("bot.log"):
            bot.create_bot()

        self.assertEqual(
            self.apihelper_module.proxy,
            {
                "http": "socks5://user:pass@185.242.107.204:52398",
                "https": "socks5://user:pass@185.242.107.204:52398",
            },
        )


if __name__ == "__main__":
    unittest.main()
