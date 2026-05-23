import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_review.services import artifact_extraction_review


class ArtifactExtractionReviewServiceTest(unittest.TestCase):
    def test_available_sessions_finds_artifact_extraction_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "session20_artifacts.json").write_text("{}", encoding="utf-8")
            (base / "session21_artifacts.json").write_text("{}", encoding="utf-8")
            (base / "session21_artifacts_metadata.json").write_text("{}", encoding="utf-8")
            (base / "session21_artifacts_reviewed.json").write_text("{}", encoding="utf-8")
            with patch.object(artifact_extraction_review, "output_path", return_value=base / "session00_artifacts.json"):
                sessions = artifact_extraction_review.available_sessions()

        self.assertEqual(sessions, [20, 21])

    def test_apply_known_update_appends_note_and_updates_flags(self):
        detail = {
            "id": 5,
            "name": "Acheron Blade",
            "artifact_type_id": None,
            "discovered_session": None,
            "description": "Black blade.",
            "lore_significance": "",
            "is_sentient": False,
            "is_cursed": False,
            "is_infernal": False,
            "notes": "",
        }
        item = {
            "artifact_id": 5,
            "new_information": "Clarified as an Acheron-touched +1 weapon.",
            "artifact_type": "weapon",
            "current_holder": "Faban",
            "properties": ["+1 weapon"],
            "is_infernal": True,
            "session_number": 21,
            "evidence": "Faban clarified the Acheron Blade.",
        }
        with patch("web_review.services.canon.artifact_detail", return_value=detail), \
             patch("web_review.services.canon.artifact_type_id", return_value=2), \
             patch("web_review.services.canon.update_artifact") as update:
            message = artifact_extraction_review.apply_known_update(21, item)

        self.assertEqual(message, "Updated Acheron Blade")
        values = update.call_args.args[1]
        self.assertEqual(values["artifact_type_id"], 2)
        self.assertTrue(values["is_infernal"])
        self.assertIn("Clarified as an Acheron-touched", values["notes"])

    def test_create_candidate_writes_artifact_values(self):
        candidate = {
            "proposed_name": "Cap of Water Breathing",
            "artifact_type": "clothing",
            "description": "Lets Mikani breathe underwater.",
            "lore_significance": "Balrog gift for the Catur mission.",
            "discovered_session": 20,
            "current_holder": "Mikani",
            "properties": ["underwater breathing"],
            "is_sentient": False,
            "is_cursed": False,
            "is_infernal": False,
            "evidence": "Mikani has a cap.",
        }
        with patch("web_review.services.canon.artifact_type_id", return_value=4), \
             patch("web_review.services.canon.create_artifact") as create:
            message = artifact_extraction_review.create_candidate(21, candidate)

        self.assertEqual(message, "Created Cap of Water Breathing")
        values = create.call_args.args[0]
        self.assertEqual(values["name"], "Cap of Water Breathing")
        self.assertEqual(values["artifact_type_id"], 4)
        self.assertEqual(values["discovered_session"], 20)
        self.assertFalse(values["is_infernal"])

    def test_apply_review_writes_decision_audit_file(self):
        extraction = {
            "known_artifact_mentions": [{"artifact_id": 5, "canonical_name": "Acheron Blade"}],
            "new_artifact_candidates": [{"proposed_name": "Cap of Water Breathing"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            reviewed_path = Path(tmp) / "session21_artifacts_reviewed.json"
            with patch.object(artifact_extraction_review, "load_extraction", return_value=extraction), \
                 patch.object(artifact_extraction_review, "reviewed_output_path", return_value=reviewed_path), \
                 patch.object(artifact_extraction_review, "apply_known_update", return_value="Updated Acheron Blade"), \
                 patch.object(artifact_extraction_review, "create_candidate", return_value="Created Cap of Water Breathing"):
                result = artifact_extraction_review.apply_review(21, {
                    "known_decision_0": "append_note",
                    "new_decision_0": "create",
                })

            document = json.loads(reviewed_path.read_text(encoding="utf-8"))

        self.assertEqual(result["applied"], ["Updated Acheron Blade", "Created Cap of Water Breathing"])
        self.assertEqual(document["known_artifact_mentions"][0]["decision"], "append_note")
        self.assertEqual(document["new_artifact_candidates"][0]["decision"], "create")


if __name__ == "__main__":
    unittest.main()
