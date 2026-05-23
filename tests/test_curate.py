import unittest

from raglib.curate import canon_scrub, split_transcript


class CurateTranscriptTest(unittest.TestCase):
    def test_split_transcript_preserves_all_content(self):
        transcript = "\n\n".join(f"paragraph {index}" for index in range(20))
        chunks = split_transcript(transcript, chunk_size=80, overlap=10)

        self.assertGreater(len(chunks), 1)
        self.assertIn("paragraph 0", chunks[0])
        self.assertIn("paragraph 19", chunks[-1])

    def test_canon_scrub_normalizes_known_transcript_drift(self):
        text = "Kator and Couture worried Makani while Gildos met Utgar near Namalua."

        self.assertEqual(
            canon_scrub(text),
            "Catur and Catur worried Mikani while Gildas met Uthgar near Namaloa.",
        )


if __name__ == "__main__":
    unittest.main()
