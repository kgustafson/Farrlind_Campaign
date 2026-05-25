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

    def test_postprocess_keeps_confirmed_tavern_despite_nearby_jokes(self):
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [{
                "proposed_name": "Blood on the Vine",
                "location_type": "tavern",
                "description": "A tavern the party jokes is vegan-friendly.",
                "evidence": "They found a tavern named Blood on the Vine.",
            }],
            "rejected_candidates": [{"text": "Blood on the Vine", "reason": "Earlier model rejection."}],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "They found a tavern named Blood on the Vine. The party jokes about vine meaning wine and vegan food.",
        )

        self.assertEqual(cleaned["new_location_candidates"][0]["proposed_name"], "Blood on the Vine")
        self.assertEqual(cleaned["rejected_candidates"], [])
        self.assertEqual(warnings, [])

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

    def test_postprocess_converts_mismatched_known_mentions_to_new_candidates(self):
        document = {
            "known_location_mentions": [{
                "location_id": 9,
                "canonical_name": "Blood on the Vine",
                "location_type": "tavern",
                "new_information": "A tavern in town.",
                "confidence": "high",
                "evidence": "They found a tavern named Blood on the Vine.",
            }],
            "new_location_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(
            document,
            [{"id": 9, "name": "Town Square"}],
            "session02",
            "They found a tavern named Blood on the Vine.",
        )

        self.assertEqual(cleaned["known_location_mentions"], [])
        self.assertEqual(cleaned["new_location_candidates"][0]["proposed_name"], "Blood on the Vine")
        self.assertIn("Converted mismatched known location mention", warnings[0])

    def test_postprocess_adds_confirmed_named_tavern_from_source(self):
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, _warnings = location_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "They found a tavern named Blood on the Vine, where Dolphin recognized them.",
        )

        self.assertEqual(cleaned["new_location_candidates"][0]["proposed_name"], "Blood on the Vine")
        self.assertEqual(cleaned["new_location_candidates"][0]["location_type"], "tavern")

    def test_postprocess_recovers_village_sign_and_corrects_tavern_type(self):
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [{
                "proposed_name": "Blood on the Vine",
                "location_type": "settlement",
                "description": "A tavern in the town square where the party found a restaurant.",
                "evidence": "The party found a tavern named Blood on the Vine.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, _warnings = location_extractor.postprocess_extraction(
            document,
            [{"id": 4, "name": "Barovia"}],
            "session02",
            "A sign reads welcome to the village of Barovia. Soon, you reach the town square, spilling from a tavern named Blood on the Vine.",
        )

        by_name = {item["proposed_name"]: item for item in cleaned["new_location_candidates"]}
        self.assertEqual(by_name["Village of Barovia"]["location_type"], "village")
        self.assertEqual(by_name["Village of Barovia"]["parent_location"], "Barovia")
        self.assertEqual(by_name["Blood on the Vine"]["location_type"], "tavern")
        self.assertEqual(by_name["Blood on the Vine"]["parent_location"], "Village of Barovia")

    def test_postprocess_drops_prior_session_location_only_found_in_recap(self):
        document = {
            "known_location_mentions": [{
                "location_id": 3,
                "canonical_name": "Overseer's Manor",
                "mentioned_as": ["Overseer's Manor"],
                "new_information": "Mentioned in recap.",
                "evidence": "Overseer's Manor was mentioned in the curated packet.",
            }],
            "new_location_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(
            document,
            [{"id": 3, "name": "Overseer's Manor", "first_visited_session": 1}],
            "session02",
            "The recap mentions Overseer's Manor. The live session reaches Blood on the Vine.",
            "The live session reaches Blood on the Vine.",
        )

        self.assertEqual(cleaned["known_location_mentions"], [])
        self.assertIn("Dropped prior-session location mention", warnings[0])

    def test_postprocess_keeps_confirmed_mansion_candidate_with_name_drift(self):
        document = {
            "known_location_mentions": [],
            "new_location_candidates": [{
                "proposed_name": "Strahd von Zarkovich von Zarovich's Mansion",
                "location_type": "mansion",
                "description": "The party jokes this is part of the resort.",
                "parent_location": "Strahd von Zarkovich's Mansion",
                "evidence": "Ismark leads them toward the mansion.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = location_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "A sign reads welcome to the village of Barovia. Ismark leads you down the road to a weary-looking mansion squatting behind a rusting iron fence. Strahd and his minions have repeatedly harassed us.",
        )

        by_name = {item["proposed_name"]: item for item in cleaned["new_location_candidates"]}
        self.assertEqual(by_name["Strahd von Zarovich's Mansion"]["location_type"], "mansion")
        self.assertEqual(by_name["Strahd von Zarovich's Mansion"]["parent_location"], "Village of Barovia")
        self.assertEqual(warnings, [])

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

    def test_extract_locations_uses_raw_transcript_for_postprocess_recovery(self):
        output = {
            "known_location_mentions": [],
            "new_location_candidates": [{
                "proposed_name": "Blood on the Vine",
                "location_type": "settlement",
                "description": "A vegan restaurant.",
                "evidence": "Key Locations: Blood on the Vine",
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
            (clean / "session02_summary.md").write_text("The party goes to Blood on the Vine.", encoding="utf-8")
            (raw / "session02_transcript.txt").write_text(
                "A sign reads welcome to the village of Barovia.\n"
                "Soon, you reach the town square, spilling from a tavern named Blood on the Vine.\n",
                encoding="utf-8",
            )
            with patch.object(location_extractor, "BASE", base), \
                 patch.object(location_extractor, "CLEAN", clean), \
                 patch.object(location_extractor, "RAW", raw), \
                 patch.object(location_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(location_extractor, "load_campaign_metadata", return_value={"party": []}), \
                 patch.object(location_extractor, "location_registry", return_value=[]), \
                 patch.object(location_extractor, "npc_name_registry", return_value=[]), \
                 patch("raglib.location_extractor.generate", return_value=json.dumps(output)):
                path = location_extractor.extract_locations("session02", model="test-model")

            document = json.loads(path.read_text(encoding="utf-8"))

        by_name = {item["proposed_name"]: item for item in document["new_location_candidates"]}
        self.assertEqual(by_name["Blood on the Vine"]["location_type"], "tavern")
        self.assertEqual(by_name["Blood on the Vine"]["description"], "A tavern named Blood on the Vine.")
        self.assertEqual(by_name["Village of Barovia"]["location_type"], "village")


if __name__ == "__main__":
    unittest.main()
