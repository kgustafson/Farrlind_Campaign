import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import lore_item_extractor


class LoreItemExtractorTest(unittest.TestCase):
    def test_extract_json_object_accepts_fenced_json(self):
        document = lore_item_extractor.extract_json_object("""```json
{"known_lore_mentions": [], "new_lore_candidates": [], "rejected_candidates": [], "uncertainties": []}
```""")
        self.assertEqual(document["known_lore_mentions"], [])

    def test_postprocess_moves_existing_candidate_to_known_mention(self):
        registry = [{"id": 5, "title": "Catur Distrusts Above-Folk", "category": "culture", "is_confirmed": True}]
        document = {
            "known_lore_mentions": [],
            "new_lore_candidates": [{
                "proposed_title": "Catur Distrusts Above-Folk",
                "category": "culture",
                "description": "Catur distrusts surface dwellers.",
                "is_confirmed": True,
                "confidence": "high",
                "evidence": "Catur does not like outsiders.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = lore_item_extractor.postprocess_extraction(document, registry, "session21")

        self.assertEqual(cleaned["new_lore_candidates"], [])
        self.assertEqual(cleaned["known_lore_mentions"][0]["lore_item_id"], 5)
        self.assertIn("Moved existing lore candidate", warnings[0])

    def test_postprocess_rejects_candidate_without_title(self):
        document = {
            "known_lore_mentions": [],
            "new_lore_candidates": [{"description": "A title-free fragment."}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = lore_item_extractor.postprocess_extraction(document, [], "session21")

        self.assertEqual(cleaned["new_lore_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "unknown candidate")
        self.assertIn("missing proposed title", warnings[0])

    def test_extract_lore_items_writes_review_json(self):
        output = {
            "known_lore_mentions": [],
            "new_lore_candidates": [{
                "proposed_title": "Celestial Isles Are Draconic",
                "category": "culture",
                "description": "The Celestial Isles are home to dragonborn and kobolds.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "knowledge" / "Faban"
            clean = base / "clean"
            raw = base / "raw"
            clean.mkdir(parents=True)
            raw.mkdir()
            (base / "final").mkdir()
            (base / "final" / "session21_summary.md").write_text("The Celestial Isles are home to dragonborn and kobolds.", encoding="utf-8")
            with patch.object(lore_item_extractor, "BASE", base), \
                 patch.object(lore_item_extractor, "CLEAN", clean), \
                 patch.object(lore_item_extractor, "RAW", raw), \
                 patch.object(lore_item_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(lore_item_extractor, "load_campaign_metadata", return_value={"party": []}), \
                 patch.object(lore_item_extractor, "lore_registry", return_value=[]), \
                 patch("web_review.services.canon.npc_rows", return_value=[]), \
                 patch("web_review.services.canon.locations", return_value=[]), \
                 patch("web_review.services.canon.artifact_rows", return_value=[]), \
                 patch("raglib.lore_item_extractor.generate", return_value=json.dumps(output)):
                path = lore_item_extractor.extract_lore_items("session21", model="test-model")

            document = json.loads(path.read_text(encoding="utf-8"))
            metadata = json.loads(path.with_name("session21_lore_items_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(document["new_lore_candidates"][0]["proposed_title"], "Celestial Isles Are Draconic")
        self.assertEqual(metadata["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
