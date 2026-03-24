import unittest
from unittest.mock import patch

from utils.logging_utils import log_event, new_operation_id


class LogEventTests(unittest.TestCase):
    def test_new_operation_id_uses_prefix(self):
        op_id = new_operation_id("media")
        self.assertTrue(op_id.startswith("media-"))

    def test_log_event_formats_key_value_payload(self):
        with patch("utils.logging_utils.log") as log_mock:
            log_event("sample_event", level="WARNING", op="op-123", chat_id=42, ok=True)

        log_mock.assert_called_once()
        message = log_mock.call_args.args[0]
        level = log_mock.call_args.kwargs["level"]

        self.assertIn("event=sample_event", message)
        self.assertIn("op=op-123", message)
        self.assertIn("chat_id=42", message)
        self.assertIn("ok=true", message)
        self.assertEqual(level, "WARNING")


if __name__ == "__main__":
    unittest.main()
