import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import location_extractor


class LocationExtractorTest(unittest.TestCase):
    def test_extract_json_object_accepts_fenced_json(self):
        document = location_extractor.extract_json_object("""```json
{"known_location_mentions": [], "new_location_candidates": [], "rejected_candidates": [], "uncertainties": []}
```""")
        self.assertEqual(document["known_location_mentions"], [])

    def test_postprocess_moves_existing_candidate_to_known_mention(self):
        registry = [{"id": 5, "name": "Catur", "location_type": "city", "parent_location": "", "is_underwater": True, "is_feywild": False}]
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [{
                "proposed_name": "Catur",
                "location_type": "city",
                "description": "Underwater city reached by the party.",
                "parent_location": "",
                "is_underwater": True,
                "is_feywild": False,
                "confidence": "high",
                "evidence": "Once in Catur...",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(document, registry, "session21", "Once in Catur, the group entered an underwater city.")

        self.assertEqual(cleaned["new_location_candidates"], [])
        self.assertEqual(cleaned["known_location_mentions"][0]["location_id"], 5)
        self.assertIn("Moved existing location candidate", warnings[0])

    def test_postprocess_normalizes_cater_to_catur(self):
        registry = [{"id": 5, "name": "Catur"}]
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [{"proposed_name": "Cater", "description": "Typo for Catur."}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, _warnings = location_extractor.postprocess_extraction(document, registry, "session21", "The party approached Cater.")

        self.assertEqual(cleaned["known_location_mentions"][0]["canonical_name"], "Catur")

    def test_postprocess_rejects_candidate_not_in_source(self):
        registry = []
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [{"proposed_name": "Imaginary City"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(document, registry, "session21", "Only Catur is mentioned.")

        self.assertEqual(cleaned["new_location_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Imaginary City")
        self.assertIn("not present", warnings[0])

    def test_postprocess_rejects_party_interpretation_location(self):
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [{
                "proposed_name": "Resort Management Office",
                "description": "The party jokingly assumes the castle is the resort management office.",
                "evidence": "They call it the manager's office as a joke.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "The party jokingly calls the castle the Resort Management Office, but no real place by that name is confirmed.",
        )

        self.assertEqual(cleaned["new_location_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Resort Management Office")
        self.assertIn("party-interpretation location", warnings[0])

    def test_postprocess_converts_unknown_known_mentions_to_new_candidates(self):
        document = {
            "known_location_mentions": [
                {
                    "location_id": 1,
                    "canonical_name": "Night Lotus Inn and Spa",
                    "new_information": "The party stayed at the resort.",
                    "location_type": "building",
                    "parent_location": "Icewind Dale",
                    "is_underwater": False,
                    "is_feywild": False,
                    "confidence": "high",
                    "evidence": "The party stayed at the Night Lotus Inn and Spa.",
                }
            ],
            "new_location_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(
            document,
            [],
            "session01",
            "The party stayed at the Night Lotus Inn and Spa in Icewind Dale.",
        )

        self.assertEqual(cleaned["known_location_mentions"], [])
        self.assertEqual(cleaned["new_location_candidates"][0]["proposed_name"], "Night Lotus Inn and Spa")
        self.assertEqual(cleaned["new_location_candidates"][0]["first_visited_session"], 1)
        self.assertIn("Converted unknown known location mention", warnings[0])

    def test_extract_locations_writes_review_json(self):
        output = {
            "known_location_mentions": [],
            "new_location_candidates": [{"proposed_name": "Catur's Well Chamber", "description": "Underwater well chamber."}],
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
            (base / "final" / "session21_summary.md").write_text("The party entered Catur's Well Chamber.", encoding="utf-8")
            with patch.object(location_extractor, "BASE", base), \
                 patch.object(location_extractor, "CLEAN", clean), \
                 patch.object(location_extractor, "RAW", raw), \
                 patch.object(location_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(location_extractor, "load_campaign_metadata", return_value={"party": []}), \
                 patch.object(location_extractor, "location_registry", return_value=[]), \
                 patch.object(location_extractor, "npc_name_registry", return_value=[]), \
                 patch("raglib.location_extractor.generate", return_value=json.dumps(output)):
                path = location_extractor.extract_locations("session21", model="test-model")

            document = json.loads(path.read_text(encoding="utf-8"))
            metadata = json.loads(path.with_name("session21_locations_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(document["new_location_candidates"][0]["proposed_name"], "Catur's Well Chamber")
        self.assertEqual(metadata["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
