import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import campaign_bootstrap_extractor as extractor


class CampaignBootstrapExtractorTest(unittest.TestCase):
    def test_available_session_names_discovers_first_source_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final = root / "final"
            clean = root / "clean"
            raw = root / "raw"
            for path in [final, clean, raw]:
                path.mkdir(parents=True)
            (raw / "session03_transcript.txt").write_text("three", encoding="utf-8")
            (clean / "session01_diary.md").write_text("one", encoding="utf-8")
            (final / "session02_summary.md").write_text("two", encoding="utf-8")

            with patch("raglib.campaign.final_dir", return_value=final), \
                 patch("raglib.campaign.clean_dir", return_value=clean), \
                 patch("raglib.campaign.raw_dir", return_value=raw):
                self.assertEqual(extractor.available_session_names(limit=2), ["session01", "session02"])

    def test_load_session_sources_uses_priority_sources_per_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            final = root / "final"
            clean = root / "clean"
            raw = root / "raw"
            for path in [final, clean, raw]:
                path.mkdir(parents=True)
            (final / "session01_summary.md").write_text("final", encoding="utf-8")
            (clean / "session01_diary.md").write_text("diary", encoding="utf-8")
            (raw / "session01_transcript.txt").write_text("transcript", encoding="utf-8")

            with patch("raglib.campaign.final_dir", return_value=final), \
                 patch("raglib.campaign.clean_dir", return_value=clean), \
                 patch("raglib.campaign.raw_dir", return_value=raw):
                sources = extractor.load_session_sources(["session01"])

        self.assertEqual([source["label"] for source in sources], ["final_summary", "diary"])
        self.assertEqual([source["text"] for source in sources], ["final", "diary"])

    def test_normalize_extraction_keeps_reviewable_shape(self):
        normalized = extractor.normalize_extraction({
            "campaign_candidates": {
                "name": {"value": "Trinyvale", "confidence": "HIGH", "evidence": "intro"},
            },
            "dm_candidates": [{"name": "Murph", "confidence": "high", "evidence": "DM intro"}],
            "party_candidates": [{
                "character_name": "Nyack",
                "player_name": "Jake",
                "aliases": "Nyak",
                "confidence": "certain",
            }],
            "glossary_candidates": [{"term": "Trinyvale", "aliases": ["Trinnyvale"]}],
            "extra": "ignored",
        })

        self.assertEqual(list(normalized.keys()), extractor.EXPECTED_TOP_LEVEL_KEYS)
        self.assertEqual(normalized["campaign_candidates"]["name"]["confidence"], "high")
        self.assertEqual(normalized["party_candidates"][0]["aliases"], ["Nyak"])
        self.assertEqual(normalized["party_candidates"][0]["confidence"], "medium")

    def test_extract_campaign_bootstrap_writes_output_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            extracted = root / "extracted"
            clean.mkdir()
            extracted.mkdir()
            (clean / "session01_diary.md").write_text("Jake plays Nyack the ranger.", encoding="utf-8")
            (root / "campaign.yaml").write_text("campaign:\n  id: trinyvale\n", encoding="utf-8")
            model_output = {
                "campaign_candidates": {"name": {"value": "Trinyvale", "confidence": "high", "evidence": "title"}},
                "dm_candidates": [],
                "party_candidates": [{"character_name": "Nyack", "player_name": "Jake", "class": "ranger", "confidence": "high", "evidence": "intro"}],
                "glossary_candidates": [],
                "rejected_candidates": [],
                "uncertainties": [],
            }

            with patch("raglib.campaign.clean_dir", return_value=clean), \
                 patch("raglib.campaign.final_dir", return_value=root / "final"), \
                 patch("raglib.campaign.raw_dir", return_value=root / "raw"), \
                 patch("raglib.campaign.extracted_dir", return_value=extracted), \
                 patch("raglib.campaign.campaign_metadata_path", return_value=root / "campaign.yaml"), \
                 patch("raglib.campaign.active_campaign_name", return_value="trinyvale"), \
                 patch("raglib.campaign_bootstrap_extractor.generate", return_value=json.dumps(model_output)):
                path = extractor.extract_campaign_bootstrap(["session01"], model="test-model")
                written = json.loads(path.read_text(encoding="utf-8"))
                metadata_exists = (extracted / "campaign_bootstrap_metadata.json").exists()

        self.assertEqual(path, extracted / "campaign_bootstrap.json")
        self.assertEqual(written["party_candidates"][0]["character_name"], "Nyack")
        self.assertTrue(metadata_exists)


if __name__ == "__main__":
    unittest.main()
