import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_review.services import npc_extraction_review


class NPCExtractionReviewServiceTest(unittest.TestCase):
    def test_append_note_adds_once(self):
        self.assertEqual(npc_extraction_review.append_note("", "Session 21: note"), "Session 21: note")
        self.assertEqual(
            npc_extraction_review.append_note("Session 21: note", "Session 21: note"),
            "Session 21: note",
        )
        self.assertEqual(
            npc_extraction_review.append_note("Earlier note", "Session 21: note"),
            "Earlier note\nSession 21: note",
        )

    def test_available_sessions_finds_extraction_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "session19_npcs.json").write_text("{}", encoding="utf-8")
            (base / "session21_npcs.json").write_text("{}", encoding="utf-8")
            (base / "session21_npcs_metadata.json").write_text("{}", encoding="utf-8")
            (base / "session21_npcs_reviewed.json").write_text("{}", encoding="utf-8")
            with patch.object(npc_extraction_review, "output_path", return_value=base / "session00_npcs.json"):
                sessions = npc_extraction_review.available_sessions()

        self.assertEqual(sessions, [19, 21])

    def test_apply_known_update_appends_note_and_updates_location(self):
        detail = {
            "id": 12,
            "name": "Alistair",
            "alias": "",
            "faction_id": None,
            "entity_status_id": 1,
            "last_known_location_id": None,
            "first_seen_session": 20,
            "description": "Boat contact.",
            "is_named": True,
            "notes": "",
        }
        item = {
            "npc_id": 12,
            "new_information": "Warned that Catur dislikes outsiders.",
            "location": "Coast near Catur",
            "evidence": "Allister warned Faban.",
        }
        with patch("web_review.services.canon.npc_detail", return_value=detail), \
             patch("web_review.services.canon.location_id", return_value=33), \
             patch("web_review.services.canon.update_npc") as update:
            message = npc_extraction_review.apply_known_update(21, item)

        self.assertEqual(message, "Updated Alistair")
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], 12)
        values = update.call_args.args[1]
        self.assertEqual(values["last_known_location_id"], 33)
        self.assertIn("Warned that Catur dislikes outsiders.", values["notes"])

    def test_create_candidate_writes_npc_values(self):
        candidate = {
            "proposed_name": "Uthgar",
            "aliases": [],
            "npc_kind": "named_npc",
            "role": "Catur smith",
            "description": "Underwater smith contact.",
            "first_seen_session": 21,
            "first_seen_location": "Catur",
            "status": "alive",
            "evidence": "They learned the smith was Uthgar.",
        }
        with patch("web_review.services.canon.location_id", return_value=44), \
             patch("web_review.services.canon.entity_status_id", return_value=2), \
             patch("web_review.services.canon.create_npc") as create:
            message = npc_extraction_review.create_candidate(21, candidate)

        self.assertEqual(message, "Created Uthgar")
        create.assert_called_once()
        values = create.call_args.args[0]
        self.assertEqual(values["name"], "Uthgar")
        self.assertEqual(values["entity_status_id"], 2)
        self.assertEqual(values["last_known_location_id"], 44)
        self.assertEqual(values["first_seen_session"], 21)
        self.assertTrue(values["is_named"])

    def test_apply_review_writes_decision_audit_file(self):
        extraction = {
            "known_npc_mentions": [{"npc_id": 12, "canonical_name": "Alistair"}],
            "new_npc_candidates": [{"proposed_name": "Uthgar"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            reviewed_path = Path(tmp) / "session21_npcs_reviewed.json"
            with patch.object(npc_extraction_review, "load_extraction", return_value=extraction), \
                 patch.object(npc_extraction_review, "reviewed_output_path", return_value=reviewed_path), \
                 patch.object(npc_extraction_review, "apply_known_update", return_value="Updated Alistair"), \
                 patch.object(npc_extraction_review, "create_candidate", return_value="Created Uthgar"):
                result = npc_extraction_review.apply_review(21, {
                    "known_decision_0": "append_note",
                    "new_decision_0": "create",
                })

            document = json.loads(reviewed_path.read_text(encoding="utf-8"))

        self.assertEqual(result["applied"], ["Updated Alistair", "Created Uthgar"])
        self.assertEqual(document["known_npc_mentions"][0]["decision"], "append_note")
        self.assertEqual(document["new_npc_candidates"][0]["decision"], "create")


if __name__ == "__main__":
    unittest.main()
