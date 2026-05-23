import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import combat_encounter_extractor


class CombatEncounterExtractorTest(unittest.TestCase):
    def test_extract_json_object_accepts_fenced_json(self):
        document = combat_encounter_extractor.extract_json_object("""```json
{"proposed_combat_encounters": [], "rejected_candidates": [], "uncertainties": []}
```""")
        self.assertEqual(document["proposed_combat_encounters"], [])

    def test_postprocess_leaves_unknown_quantity_blank(self):
        document = {
            "proposed_combat_encounters": [{
                "title": "Cultist battle",
                "session_number": 19,
                "enemies": [{"name": "Cultist", "quantity": "unknown", "outcome": ""}],
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = combat_encounter_extractor.postprocess_extraction(document, "session19")

        self.assertEqual(warnings, [])
        enemy = cleaned["proposed_combat_encounters"][0]["enemies"][0]
        self.assertIsNone(enemy["quantity"])
        self.assertEqual(enemy["outcome"], "unknown")

    def test_postprocess_rejects_untitled_encounter(self):
        document = {
            "proposed_combat_encounters": [{"enemies": [{"name": "Cultist"}], "evidence": "A fight happened."}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = combat_encounter_extractor.postprocess_extraction(document, "session19")

        self.assertEqual(cleaned["proposed_combat_encounters"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["reason"], "Combat encounter candidate is missing a title.")
        self.assertIn("missing title", warnings[0])

    def test_postprocess_rejects_wrong_session_candidates(self):
        document = {
            "proposed_combat_encounters": [{"title": "Old fight", "session_number": 3, "enemies": [{"name": "Goblin"}]}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = combat_encounter_extractor.postprocess_extraction(document, "session21")

        self.assertEqual(cleaned["proposed_combat_encounters"], [])
        self.assertIn("not 21", cleaned["rejected_candidates"][0]["reason"])
        self.assertIn("wrong session", warnings[0])

    def test_extract_combat_encounters_writes_review_json(self):
        output = {
            "proposed_combat_encounters": [{
                "title": "Orsydon summoned in Balrog",
                "session_number": 19,
                "location": "Balrog",
                "enemies": [{"name": "Orsydon", "quantity": 1, "outcome": "defeated"}],
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
            (base / "final" / "session19_summary.md").write_text("The party defeated Orsydon in Balrog.", encoding="utf-8")
            with patch.object(combat_encounter_extractor, "BASE", base), \
                 patch.object(combat_encounter_extractor, "CLEAN", clean), \
                 patch.object(combat_encounter_extractor, "RAW", raw), \
                 patch.object(combat_encounter_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(combat_encounter_extractor, "load_campaign_metadata", return_value={"party": []}), \
                 patch("web_review.services.canon.locations", return_value=["Balrog"]), \
                 patch("raglib.combat_encounter_extractor.generate", return_value=json.dumps(output)):
                path = combat_encounter_extractor.extract_combat_encounters("session19", model="test-model")

            document = json.loads(path.read_text(encoding="utf-8"))
            metadata = json.loads(path.with_name("session19_combat_encounters_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(document["proposed_combat_encounters"][0]["title"], "Orsydon summoned in Balrog")
        self.assertEqual(metadata["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
