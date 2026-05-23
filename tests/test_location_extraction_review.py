import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_review.services import location_extraction_review


class LocationExtractionReviewServiceTest(unittest.TestCase):
    def test_available_sessions_finds_location_extraction_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "session20_locations.json").write_text("{}", encoding="utf-8")
            (base / "session21_locations.json").write_text("{}", encoding="utf-8")
            (base / "session21_locations_metadata.json").write_text("{}", encoding="utf-8")
            (base / "session21_locations_reviewed.json").write_text("{}", encoding="utf-8")
            with patch.object(location_extraction_review, "output_path", return_value=base / "session00_locations.json"):
                sessions = location_extraction_review.available_sessions()

        self.assertEqual(sessions, [20, 21])

    def test_apply_known_update_appends_note_and_updates_metadata(self):
        detail = {
            "id": 5,
            "name": "Catur",
            "location_type_id": None,
            "parent_location_id": None,
            "description": "Sunken city.",
            "is_underwater": False,
            "is_feywild": False,
            "first_visited_session": None,
            "notes": "",
        }
        item = {
            "location_id": 5,
            "new_information": "Confirmed as an underwater city.",
            "location_type": "city",
            "parent_location": "",
            "is_underwater": True,
            "is_feywild": False,
            "session_number": 21,
            "evidence": "Catur lies beneath the ocean.",
        }
        with patch("web_review.services.canon.location_detail", return_value=detail), \
             patch("web_review.services.canon.location_type_id", return_value=2), \
             patch("web_review.services.canon.location_id", return_value=None), \
             patch("web_review.services.canon.update_location") as update:
            message = location_extraction_review.apply_known_update(21, item)

        self.assertEqual(message, "Updated Catur")
        values = update.call_args.args[1]
        self.assertEqual(values["location_type_id"], 2)
        self.assertTrue(values["is_underwater"])
        self.assertEqual(values["first_visited_session"], 21)
        self.assertIn("Confirmed as an underwater city.", values["notes"])

    def test_create_candidate_writes_location_values(self):
        candidate = {
            "proposed_name": "Catur's Well Chamber",
            "location_type": "chamber",
            "description": "Underwater well chamber.",
            "first_visited_session": 21,
            "parent_location": "Catur",
            "is_underwater": True,
            "is_feywild": False,
            "evidence": "The party entered the well chamber.",
        }
        with patch("web_review.services.canon.location_type_id", return_value=4), \
             patch("web_review.services.canon.location_id", return_value=5), \
             patch("web_review.services.canon.create_location") as create:
            message = location_extraction_review.create_candidate(21, candidate)

        self.assertEqual(message, "Created Catur's Well Chamber")
        values = create.call_args.args[0]
        self.assertEqual(values["name"], "Catur's Well Chamber")
        self.assertEqual(values["location_type_id"], 4)
        self.assertEqual(values["parent_location_id"], 5)
        self.assertTrue(values["is_underwater"])

    def test_apply_review_writes_decision_audit_file(self):
        extraction = {
            "known_location_mentions": [{"location_id": 5, "canonical_name": "Catur"}],
            "new_location_candidates": [{"proposed_name": "Catur's Well Chamber"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            reviewed_path = Path(tmp) / "session21_locations_reviewed.json"
            with patch.object(location_extraction_review, "load_extraction", return_value=extraction), \
                 patch.object(location_extraction_review, "reviewed_output_path", return_value=reviewed_path), \
                 patch.object(location_extraction_review, "apply_known_update", return_value="Updated Catur"), \
                 patch.object(location_extraction_review, "create_candidate", return_value="Created Catur's Well Chamber"):
                result = location_extraction_review.apply_review(21, {
                    "known_decision_0": "append_note",
                    "new_decision_0": "create",
                })

            document = json.loads(reviewed_path.read_text(encoding="utf-8"))

        self.assertEqual(result["applied"], ["Updated Catur", "Created Catur's Well Chamber"])
        self.assertEqual(document["known_location_mentions"][0]["decision"], "append_note")
        self.assertEqual(document["new_location_candidates"][0]["decision"], "create")


if __name__ == "__main__":
    unittest.main()
