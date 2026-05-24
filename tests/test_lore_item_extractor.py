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

        cleaned, warnings = lore_item_extractor.postprocess_extraction(
            document,
            registry,
            "session21",
            "Catur Distrusts Above-Folk. Catur does not like outsiders.",
        )

        self.assertEqual(cleaned["new_lore_candidates"], [])
        self.assertEqual(cleaned["known_lore_mentions"][0]["lore_item_id"], 5)
        self.assertIn("Moved existing lore candidate", warnings[0])

    def test_postprocess_drops_known_lore_absent_from_source(self):
        registry = [{"id": 3, "title": "Wand of Wells Required", "category": "magic", "is_confirmed": True}]
        document = {
            "known_lore_mentions": [{
                "lore_item_id": 3,
                "canonical_title": "Wand of Wells Required",
                "new_information": "Guests surrender weapons at a spa.",
            }],
            "new_lore_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = lore_item_extractor.postprocess_extraction(
            document,
            registry,
            "session01",
            "The Night Lotus asks guests to surrender weapons and magic items.",
        )

        self.assertEqual(cleaned["known_lore_mentions"], [])
        self.assertIn("not present in session source", warnings[0])

    def test_postprocess_rejects_unconfirmed_party_interpretation_lore(self):
        document = {
            "known_lore_mentions": [],
            "new_lore_candidates": [{
                "proposed_title": "Burgomaster Means Burger Master",
                "category": "canon_ambiguity",
                "description": "The party mistakenly interprets Burgomaster as a burger title.",
                "is_confirmed": False,
                "evidence": "The party misreads Burgomaster as Burger Master.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = lore_item_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "The party misreads Burgomaster as Burger Master and jokes about a secret recipe.",
        )

        self.assertEqual(cleaned["new_lore_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Burgomaster Means Burger Master")
        self.assertIn("party-interpretation lore", warnings[0])

    def test_postprocess_converts_unknown_known_mentions_to_new_candidates(self):
        document = {
            "known_lore_mentions": [{
                "lore_item_id": 9,
                "canonical_title": "The Night Lotus Policy",
                "new_information": "The Night Lotus asks guests to surrender weapons and magic items.",
                "session_number": 1,
                "category": "culture",
                "source_npc": "Reagan",
                "is_confirmed": True,
                "confidence": "high",
                "evidence": "The Night Lotus asks guests to surrender weapons and magic items.",
            }],
            "new_lore_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = lore_item_extractor.postprocess_extraction(
            document,
            [],
            "session01",
            "Reagan explains The Night Lotus Policy: guests surrender weapons and magic items.",
        )

        self.assertEqual(cleaned["known_lore_mentions"], [])
        self.assertEqual(cleaned["new_lore_candidates"][0]["proposed_title"], "The Night Lotus Policy")
        self.assertIn("Converted unknown known lore mention", warnings[0])

    def test_postprocess_converts_unknown_known_mentions_when_evidence_is_grounded(self):
        document = {
            "known_lore_mentions": [{
                "lore_item_id": 9,
                "canonical_title": "The Night Lotus Policy",
                "new_information": "Guests must surrender weapons and magic items.",
                "session_number": 1,
                "category": "culture",
                "source_npc": "Reagan",
                "is_confirmed": True,
                "confidence": "high",
                "evidence": "Reagan established a policy requiring visitors to surrender weapons and magic items during their stay.",
            }],
            "new_lore_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = lore_item_extractor.postprocess_extraction(
            document,
            [],
            "session01",
            "Reagan established a policy requiring visitors to surrender weapons and magic items during their stay.",
        )

        self.assertEqual(cleaned["new_lore_candidates"][0]["proposed_title"], "The Night Lotus Policy")
        self.assertIn("Converted unknown known lore mention", warnings[0])

    def test_postprocess_converts_mismatched_known_mentions_to_new_candidates(self):
        registry = [{"id": 1, "title": "The Night Lotus Policy", "category": "culture", "is_confirmed": True}]
        document = {
            "known_lore_mentions": [{
                "lore_item_id": 1,
                "canonical_title": "Barovia Revelation",
                "new_information": "The gate leads into Barovia.",
                "session_number": 1,
                "category": "location_lore",
                "source_npc": "",
                "is_confirmed": True,
                "confidence": "high",
                "evidence": "The gate leads into Barovia.",
            }],
            "new_lore_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = lore_item_extractor.postprocess_extraction(
            document,
            registry,
            "session01",
            "The gate leads into Barovia. Barovia Revelation.",
        )

        self.assertEqual(cleaned["known_lore_mentions"], [])
        self.assertEqual(cleaned["new_lore_candidates"][0]["proposed_title"], "Barovia Revelation")
        self.assertIn("Converted mismatched known lore mention", warnings[0])

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
