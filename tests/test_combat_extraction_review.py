import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_review.services import combat_extraction_review


class CombatExtractionReviewServiceTest(unittest.TestCase):
    def test_available_sessions_finds_combat_extraction_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "session19_combat_encounters.json").write_text("{}", encoding="utf-8")
            (base / "session20_combat_encounters.json").write_text("{}", encoding="utf-8")
            (base / "session20_combat_encounters_metadata.json").write_text("{}", encoding="utf-8")
            (base / "session20_combat_encounters_reviewed.json").write_text("{}", encoding="utf-8")
            with patch.object(combat_extraction_review, "output_path", return_value=base / "session00_combat_encounters.json"):
                sessions = combat_extraction_review.available_sessions()

        self.assertEqual(sessions, [19, 20])

    def test_create_candidate_writes_parent_and_enemy_rows(self):
        candidate = {
            "title": "Orsydon summoned in Balrog",
            "session_number": 19,
            "subtype": "dragon_summoning",
            "location": "Balrog",
            "participants": "Party, Orsydon, cultists",
            "outcome": "enemies_defeated",
            "confidence": "high",
            "notes": "The party defeated Orsydon.",
            "enemies": [{"name": "Orsydon", "enemy_type": "dragon", "quantity": 1, "outcome": "defeated"}],
        }
        with patch("web_review.services.canon.location_id", return_value=4), \
             patch("web_review.services.canon.create_combat_encounter") as create:
            message = combat_extraction_review.create_candidate(19, candidate)

        self.assertEqual(message, "Created Orsydon summoned in Balrog")
        values, enemies = create.call_args.args
        self.assertEqual(values["location_id"], 4)
        self.assertEqual(enemies[0]["name"], "Orsydon")
        self.assertEqual(enemies[0]["quantity"], 1)

    def test_apply_review_writes_decision_audit_file(self):
        extraction = {
            "proposed_combat_encounters": [{"title": "Orsydon summoned in Balrog"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            reviewed_path = Path(tmp) / "session19_combat_encounters_reviewed.json"
            with patch.object(combat_extraction_review, "load_extraction", return_value=extraction), \
                 patch.object(combat_extraction_review, "reviewed_output_path", return_value=reviewed_path), \
                 patch.object(combat_extraction_review, "create_candidate", return_value="Created Orsydon summoned in Balrog"):
                result = combat_extraction_review.apply_review(19, {"encounter_decision_0": "create"})

            document = json.loads(reviewed_path.read_text(encoding="utf-8"))

        self.assertEqual(result["applied"], ["Created Orsydon summoned in Balrog"])
        self.assertEqual(document["proposed_combat_encounters"][0]["decision"], "create")


if __name__ == "__main__":
    unittest.main()
