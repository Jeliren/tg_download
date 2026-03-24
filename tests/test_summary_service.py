import unittest
from unittest import mock

from services import summary_service


class SummaryServiceTests(unittest.TestCase):
    def test_summarize_transcript_text_single_chunk_uses_single_request(self):
        with mock.patch.object(summary_service, "_responses_create", return_value="summary") as responses_create:
            result = summary_service.summarize_transcript_text("short transcript")

        self.assertEqual(result, "summary")
        self.assertEqual(responses_create.call_count, 1)
        self.assertEqual(responses_create.call_args.kwargs["request_type"], "single")

    def test_summarize_transcript_text_rejects_empty_partial_summary(self):
        with (
            mock.patch.object(
                summary_service,
                "split_text_chunks",
                return_value=["first chunk", "second chunk"],
            ),
            mock.patch.object(summary_service, "_responses_create", return_value=""),
        ):
            with self.assertRaises(RuntimeError):
                summary_service.summarize_transcript_text("long transcript")


if __name__ == "__main__":
    unittest.main()
