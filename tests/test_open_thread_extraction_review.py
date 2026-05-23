import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_review.services import open_thread_extraction_review


class OpenThreadExtractionReviewServiceTest(unittest.TestCase):
    def statuses(self):
        return [
            {"code": "open", "label": "Open"},
            {"code": "resolved", "label": "Resolved"},
            {"code": "superseded", "label": "Superseded"},
            {"code": "unknown", "label": "Unknown"},
        ]

    def types(self):
        return ["lore_mystery", "active_threat", "pending_quest"]

    def test_available_sessions_finds_open_thread_extraction_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "session20_open_threads.json").write_text("{}", encoding="utf-8")
            (base / "session21_open_threads.json").write_text("{}", encoding="utf-8")
            (base / "session21_open_threads_metadata.json").write_text("{}", encoding="utf-8")
            (base / "session21_open_threads_reviewed.json").write_text("{}", encoding="utf-8")
            with patch.object(open_thread_extraction_review, "output_path", return_value=base / "session00_open_threads.json"):
                sessions = open_thread_extraction_review.available_sessions()

        self.assertEqual(sessions, [20, 21])

    def test_apply_known_update_appends_note_and_updates_detail(self):
        detail = {
            "id": 5,
            "title": "What does the Gale want?",
            "thread_type": "lore_mystery",
            "status": "open",
            "first_session": 20,
            "last_session": None,
            "related_location_id": None,
            "description": "The Gale may be more than weather.",
            "resolution": "",
            "notes": "",
        }
        item = {
            "thread_id": 5,
            "canonical_title": "What does the Gale want?",
            "new_information": "The party still considers the Gale an unvisited dangerous place.",
            "thread_type": "active_threat",
            "status": "open",
            "last_session": 21,
            "related_location": "The Gale",
            "evidence": "The Gale remains ahead.",
        }
        with patch("web_review.services.canon.open_thread_detail", return_value=detail), \
             patch("web_review.services.canon.location_id", return_value=9), \
             patch("web_review.services.canon.open_thread_statuses", return_value=self.statuses()), \
             patch("web_review.services.canon.open_thread_types", return_value=self.types()), \
             patch("web_review.services.canon.update_open_thread") as update:
            message = open_thread_extraction_review.apply_known_update(21, item)

        self.assertEqual(message, "Updated What does the Gale want?")
        values = update.call_args.args[1]
        self.assertEqual(values["thread_type"], "active_threat")
        self.assertEqual(values["related_location_id"], 9)
        self.assertIn("party still considers", values["description"])
        self.assertIn("Session 21", values["notes"])

    def test_create_candidate_writes_open_thread_values(self):
        candidate = {
            "proposed_title": "Niebain Warns Catur Is Already In Danger",
            "thread_type": "active_threat",
            "status": "open",
            "first_session": 21,
            "last_session": 21,
            "related_location": "Catur",
            "description": "Niebain warned that Catur was already in danger.",
            "evidence": "We are in great danger already.",
        }
        with patch("web_review.services.canon.location_id", return_value=4), \
             patch("web_review.services.canon.open_thread_statuses", return_value=self.statuses()), \
             patch("web_review.services.canon.open_thread_types", return_value=self.types()), \
             patch("web_review.services.canon.create_open_thread") as create:
            message = open_thread_extraction_review.create_candidate(21, candidate)

        self.assertEqual(message, "Created Niebain Warns Catur Is Already In Danger")
        values = create.call_args.args[0]
        self.assertEqual(values["title"], "Niebain Warns Catur Is Already In Danger")
        self.assertEqual(values["thread_type"], "active_threat")
        self.assertEqual(values["related_location_id"], 4)
        self.assertEqual(values["first_session"], 21)

    def test_apply_review_writes_decision_audit_file(self):
        extraction = {
            "known_thread_mentions": [{"thread_id": 5, "canonical_title": "What does the Gale want?"}],
            "new_thread_candidates": [{"proposed_title": "Niebain Warns Catur Is Already In Danger"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            reviewed_path = Path(tmp) / "session21_open_threads_reviewed.json"
            with patch.object(open_thread_extraction_review, "load_extraction", return_value=extraction), \
                 patch.object(open_thread_extraction_review, "reviewed_output_path", return_value=reviewed_path), \
                 patch.object(open_thread_extraction_review, "apply_known_update", return_value="Updated What does the Gale want?"), \
                 patch.object(open_thread_extraction_review, "create_candidate", return_value="Created Niebain Warns Catur Is Already In Danger"):
                result = open_thread_extraction_review.apply_review(21, {
                    "known_decision_0": "update",
                    "new_decision_0": "create",
                })

            document = json.loads(reviewed_path.read_text(encoding="utf-8"))

        self.assertEqual(result["applied"], ["Updated What does the Gale want?", "Created Niebain Warns Catur Is Already In Danger"])
        self.assertEqual(document["known_thread_mentions"][0]["decision"], "update")
        self.assertEqual(document["new_thread_candidates"][0]["decision"], "create")


if __name__ == "__main__":
    unittest.main()
