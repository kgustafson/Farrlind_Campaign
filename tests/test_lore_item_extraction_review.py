import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_review.services import lore_item_extraction_review


class LoreItemExtractionReviewServiceTest(unittest.TestCase):
    def test_available_sessions_finds_lore_item_extraction_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "session20_lore_items.json").write_text("{}", encoding="utf-8")
            (base / "session21_lore_items.json").write_text("{}", encoding="utf-8")
            (base / "session21_lore_items_metadata.json").write_text("{}", encoding="utf-8")
            (base / "session21_lore_items_reviewed.json").write_text("{}", encoding="utf-8")
            with patch.object(lore_item_extraction_review, "output_path", return_value=base / "session00_lore_items.json"):
                sessions = lore_item_extraction_review.available_sessions()

        self.assertEqual(sessions, [20, 21])

    def test_apply_known_update_appends_note_and_updates_detail(self):
        detail = {
            "id": 5,
            "title": "Catur Distrusts Above-Folk",
            "category": "culture",
            "description": "Catur distrusts surface dwellers.",
            "source_npc_id": None,
            "discovered_session": 20,
            "is_confirmed": False,
            "notes": "",
        }
        item = {
            "lore_item_id": 5,
            "new_information": "The queen limited the party's movement inside Catur.",
            "category": "culture",
            "source_npc": "Queen of Catur",
            "is_confirmed": True,
            "session_number": 21,
            "evidence": "The party was granted access to a courtyard area.",
        }
        with patch("web_review.services.canon.lore_item_detail", return_value=detail), \
             patch("web_review.services.canon.npc_rows", return_value=[{"id": 7, "name": "Queen of Catur"}]), \
             patch("web_review.services.canon.update_lore_item") as update:
            message = lore_item_extraction_review.apply_known_update(21, item)

        self.assertEqual(message, "Updated Catur Distrusts Above-Folk")
        values = update.call_args.args[1]
        self.assertEqual(values["source_npc_id"], 7)
        self.assertTrue(values["is_confirmed"])
        self.assertIn("queen limited", values["description"])
        self.assertIn("Session 21", values["notes"])

    def test_create_candidate_writes_lore_values(self):
        candidate = {
            "proposed_title": "Celestial Isles Are Draconic",
            "category": "culture",
            "description": "The Celestial Isles are home to dragonborn and kobolds.",
            "source_npc": "Mikani",
            "discovered_session": 21,
            "is_confirmed": True,
            "evidence": "The Isles are largely draconic.",
        }
        with patch("web_review.services.canon.npc_rows", return_value=[{"id": 4, "name": "Mikani"}]), \
             patch("web_review.services.canon.create_lore_item") as create:
            message = lore_item_extraction_review.create_candidate(21, candidate)

        self.assertEqual(message, "Created Celestial Isles Are Draconic")
        values = create.call_args.args[0]
        self.assertEqual(values["title"], "Celestial Isles Are Draconic")
        self.assertEqual(values["source_npc_id"], 4)
        self.assertEqual(values["discovered_session"], 21)
        self.assertTrue(values["is_confirmed"])

    def test_apply_review_writes_decision_audit_file(self):
        extraction = {
            "known_lore_mentions": [{"lore_item_id": 5, "canonical_title": "Catur Distrusts Above-Folk"}],
            "new_lore_candidates": [{"proposed_title": "Celestial Isles Are Draconic"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            reviewed_path = Path(tmp) / "session21_lore_items_reviewed.json"
            with patch.object(lore_item_extraction_review, "load_extraction", return_value=extraction), \
                 patch.object(lore_item_extraction_review, "reviewed_output_path", return_value=reviewed_path), \
                 patch.object(lore_item_extraction_review, "apply_known_update", return_value="Updated Catur Distrusts Above-Folk"), \
                 patch.object(lore_item_extraction_review, "create_candidate", return_value="Created Celestial Isles Are Draconic"):
                result = lore_item_extraction_review.apply_review(21, {
                    "known_decision_0": "append_note",
                    "new_decision_0": "create",
                })

            document = json.loads(reviewed_path.read_text(encoding="utf-8"))

        self.assertEqual(result["applied"], ["Updated Catur Distrusts Above-Folk", "Created Celestial Isles Are Draconic"])
        self.assertEqual(document["known_lore_mentions"][0]["decision"], "append_note")
        self.assertEqual(document["new_lore_candidates"][0]["decision"], "create")


if __name__ == "__main__":
    unittest.main()
