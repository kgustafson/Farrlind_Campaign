import unittest
from unittest.mock import patch

from raglib import curate


class CurateCanonScrubTest(unittest.TestCase):
    def test_canon_scrub_does_not_expand_alias_inside_existing_full_name(self):
        metadata = {
            "glossary": [
                {"term": "Strahd von Zarovich", "aliases": ["Strahd", "Strahd von Zorovich"]},
                {"term": "Marina Kulyana", "aliases": ["Marina"]},
                {"term": "Kolyan Indirovich", "aliases": ["Kolyan"]},
                {"term": "Nyack of the Ran'afor", "aliases": ["Nyack"]},
            ]
        }
        text = (
            "Strahd von Zarovich watches Strahd. "
            "Marina Kulyana speaks with Marina. "
            "Kolyan Indirovich wrote to Kolyan. "
            "Nyack of the Ran'afor helps Nyack."
        )

        with patch("raglib.curate.load_campaign_metadata", return_value=metadata):
            scrubbed = curate.canon_scrub(text)

        self.assertIn("Strahd von Zarovich watches Strahd von Zarovich.", scrubbed)
        self.assertIn("Marina Kulyana speaks with Marina Kulyana.", scrubbed)
        self.assertIn("Kolyan Indirovich wrote to Kolyan Indirovich.", scrubbed)
        self.assertIn("Nyack of the Ran'afor helps Nyack of the Ran'afor.", scrubbed)
        self.assertNotIn("von Zarovich von Zarovich", scrubbed)
        self.assertNotIn("Kulyana Kulyana", scrubbed)
        self.assertNotIn("Indirovich Indirovich", scrubbed)
        self.assertNotIn("Ran'afor of the Ran'afor", scrubbed)

    def test_collapse_repeated_canon_names_handles_existing_pollution(self):
        text = "Bluetooth (Bluetooth) saw Strahd von Zarovich von Zarovich and Marina Kulyana Kulyana."

        scrubbed = curate.collapse_repeated_canon_names(
            text,
            ["Strahd von Zarovich", "Marina Kulyana", "Bluetooth"],
        )

        self.assertEqual(scrubbed, "Bluetooth saw Strahd von Zarovich and Marina Kulyana.")


if __name__ == "__main__":
    unittest.main()
