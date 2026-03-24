import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

requests_module = types.ModuleType("requests")
requests_exceptions_module = types.ModuleType("requests.exceptions")


class DummyConnectionError(Exception):
    pass


class DummyReadTimeout(Exception):
    pass


requests_exceptions_module.ConnectionError = DummyConnectionError
requests_exceptions_module.ReadTimeout = DummyReadTimeout
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

file_utils = importlib.import_module("utils.file_utils")
cleanup_temp_folder = file_utils.cleanup_temp_folder
send_with_retry = file_utils.send_with_retry


class FileUtilsTests(unittest.TestCase):
    def test_send_with_retry_does_not_sleep_after_last_attempt(self):
        send_attempts = []

        def failing_send(*args, **kwargs):
            send_attempts.append((args, kwargs))
            raise RuntimeError("boom")

        with patch("utils.file_utils.log"), patch("utils.file_utils.time.sleep") as sleep_mock:
            result = send_with_retry(failing_send, "chat-id", max_retries=3)

        self.assertIsNone(result)
        self.assertEqual(len(send_attempts), 3)
        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_any_call(1)
        sleep_mock.assert_any_call(2)

    def test_cleanup_temp_folder_skips_unsafe_root_directory(self):
        with patch("utils.file_utils.log") as log_mock:
            cleanup_temp_folder(os.sep)

        log_mock.assert_called_once()
        self.assertIn("небезопасной временной директории", log_mock.call_args.args[0])

    def test_cleanup_temp_folder_removes_nested_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_dir = os.path.join(temp_dir, "nested")
            nested_file = os.path.join(nested_dir, "file.txt")
            os.makedirs(nested_dir, exist_ok=True)
            with open(os.path.join(temp_dir, "root.txt"), "w", encoding="utf-8") as file_obj:
                file_obj.write("root")
            with open(nested_file, "w", encoding="utf-8") as file_obj:
                file_obj.write("nested")

            cleanup_temp_folder(temp_dir)

            self.assertEqual(os.listdir(temp_dir), [])


if __name__ == "__main__":
    unittest.main()
