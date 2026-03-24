import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

requests_module = types.ModuleType("requests")
requests_exceptions_module = types.ModuleType("requests.exceptions")
requests_exceptions_module.ConnectionError = RuntimeError
requests_exceptions_module.ReadTimeout = TimeoutError
requests_module.exceptions = requests_exceptions_module
sys.modules.setdefault("requests", requests_module)
sys.modules.setdefault("requests.exceptions", requests_exceptions_module)

telebot_module = types.ModuleType("telebot")
telebot_apihelper_module = types.ModuleType("telebot.apihelper")


class DummyApiTelegramException(Exception):
    pass


telebot_apihelper_module.ApiTelegramException = DummyApiTelegramException
telebot_module.apihelper = telebot_apihelper_module
sys.modules.setdefault("telebot", telebot_module)
sys.modules.setdefault("telebot.apihelper", telebot_apihelper_module)

yt_dlp_module = types.ModuleType("yt_dlp")
yt_dlp_module.version = types.SimpleNamespace(__version__="test-version")
sys.modules.setdefault("yt_dlp", yt_dlp_module)

main = importlib.import_module("main")


class ShutdownControllerTests(unittest.TestCase):
    def test_request_shutdown_stops_polling_once(self):
        controller = main.ShutdownController()
        bot = MagicMock()
        controller.attach_bot(bot)

        with patch("main.log"):
            controller.request_shutdown("stop")
            controller.request_shutdown("stop-again")

        self.assertTrue(controller.is_requested())
        bot.stop_polling.assert_called()


class MainTests(unittest.TestCase):
    def test_main_returns_error_when_create_bot_fails(self):
        with patch("main._ensure_runtime_directories"), \
             patch("main.setup_logging"), \
             patch("main.register_signal_handlers"), \
             patch("main.get_runtime_warnings", return_value=[]), \
             patch("main.cleanup_temp_folder") as cleanup_mock, \
             patch("main.create_bot", side_effect=RuntimeError("boom")), \
             patch("main.log"):
            result = main.main()

        self.assertEqual(result, 1)
        self.assertEqual(cleanup_mock.call_count, 2)

    def test_main_returns_error_after_polling_retries_are_exhausted(self):
        bot = MagicMock()
        bot.infinity_polling.side_effect = RuntimeError("polling failed")

        with patch("main._ensure_runtime_directories"), \
             patch("main.setup_logging"), \
             patch("main.register_signal_handlers"), \
             patch("main.get_runtime_warnings", return_value=[]), \
             patch("main.cleanup_temp_folder"), \
             patch("main.create_bot", return_value=bot), \
             patch("main.MAX_POLLING_RESTARTS", 2), \
             patch("main.POLLING_RESTART_DELAY", 0), \
             patch("main.log"), \
             patch("main.log_event"):
            result = main.main()

        self.assertEqual(result, 1)
        self.assertEqual(bot.infinity_polling.call_count, 2)

    def test_main_returns_success_when_shutdown_is_requested_before_polling(self):
        bot = MagicMock()

        def register_and_request_shutdown(controller):
            controller.request_shutdown("test shutdown")

        with patch("main._ensure_runtime_directories"), \
             patch("main.setup_logging"), \
             patch("main.register_signal_handlers", side_effect=register_and_request_shutdown), \
             patch("main.get_runtime_warnings", return_value=[]), \
             patch("main.cleanup_temp_folder"), \
             patch("main.create_bot", return_value=bot), \
             patch("main.log"), \
             patch("main.log_event"):
            result = main.main()

        self.assertEqual(result, 0)
        bot.infinity_polling.assert_not_called()


if __name__ == "__main__":
    unittest.main()
