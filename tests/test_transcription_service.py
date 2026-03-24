import unittest

from services import transcription_service


class TranscriptionServiceTests(unittest.TestCase):
    def test_split_text_chunks_rejects_non_positive_chunk_size(self):
        with self.assertRaises(ValueError):
            transcription_service.split_text_chunks("text", chunk_size=0)

        with self.assertRaises(ValueError):
            transcription_service.send_text_chunks(object(), 1, "text", chunk_size=-1)

    def test_split_text_chunks_splits_long_word(self):
        chunks = transcription_service.split_text_chunks("x" * 10, chunk_size=4)

        self.assertEqual(chunks, ["xxxx", "xxxx", "xx"])


if __name__ == "__main__":
    unittest.main()
