import unittest
from unittest.mock import patch

from raglib.curate import canon_scrub, split_transcript


class CurateTranscriptTest(unittest.TestCase):
    def test_split_transcript_preserves_all_content(self):
        transcript = "\n\n".join(f"paragraph {index}" for index in range(20))
        chunks = split_transcript(transcript, chunk_size=80, overlap=10)

        self.assertGreater(len(chunks), 1)
        self.assertIn("paragraph 0", chunks[0])
        self.assertIn("paragraph 19", chunks[-1])

    def test_canon_scrub_normalizes_campaign_glossary_aliases(self):
        text = "Triniville and Jins visited Kator."

        with patch("raglib.curate.load_campaign_metadata", return_value={
            "glossary": [
                {"term": "Trinyvale", "aliases": ["Triniville"]},
                {"term": "Jens Lyndelle", "aliases": ["Jins"]},
            ],
        }):
            self.assertEqual(canon_scrub(text), "Trinyvale and Jens Lyndelle visited Kator.")


if __name__ == "__main__":
    unittest.main()
