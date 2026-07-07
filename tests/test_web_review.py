import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from web_review.services import artifact_extraction_review, canon, combat_extraction_review, commands, location_extraction_review, lore_item_extraction_review, npc_extraction_review, open_thread_extraction_review, reviews, workflow
from web_review.app import BACKUP_DOWNLOADS, COMMAND_RESULTS, app, app_git_hash_short, app_version, macro_locations_to_validate, sync_after_extraction_review
from scripts import export_static_archive, publish_static_archive
from scripts.load_songbook import songbook_source_sql
from fastapi.testclient import TestClient


class WebReviewServiceTest(unittest.TestCase):
    def write_review(self, root: Path, session: str, document: dict):
        path = root / "reviews" / f"{session}_review.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return path

    def test_dashboard_rows_summarize_review_files_and_final_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            (clean / "session02_summary.md").write_text("draft", encoding="utf-8")
            (final / "session02_summary.md").write_text("final", encoding="utf-8")
            self.write_review(root, "session02", {
                "session": "session02",
                "status": "reviewed",
                "session_title": "Road to Fey Woods",
                "items": [
                    {"id": "event-001", "decision": "accepted", "applied_status": "applied"},
                    {"id": "event-002", "decision": "corrected", "applied_status": "pending"},
                ],
                "added_items": [
                    {"id": "added-001", "decision": "added", "applied_status": "pending"},
                ],
            })

            with patch.object(reviews, "REVIEWS_DIR", root / "reviews"), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                rows = reviews.dashboard_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].session, "session02")
        self.assertEqual(rows[0].status, "reviewed")
        self.assertEqual(rows[0].total_items, 3)
        self.assertEqual(rows[0].corrected, 1)
        self.assertEqual(rows[0].added, 1)
        self.assertEqual(rows[0].unapplied_items, 2)
        self.assertTrue(rows[0].final_exists)
        self.assertEqual(rows[0].next_action, "apply")
        self.assertTrue(rows[0].event_review_ready)
        self.assertEqual(rows[0].missing_extraction_reviews, [])

    def test_dashboard_rows_mark_event_review_ready_after_extraction_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clean").mkdir()
            (root / "final").mkdir()
            extracted = root / "extracted"
            extracted.mkdir()
            (root / "clean" / "session01_summary.md").write_text("draft", encoding="utf-8")
            self.write_review(root, "session01", {"session": "session01", "status": "in_review", "items": []})
            for _label, pattern in reviews.EXTRACTION_REVIEW_FILES:
                (extracted / pattern.format(session_number=1)).write_text("{}", encoding="utf-8")

            with patch.object(reviews, "KNOWLEDGE_DIR", root), \
                 patch.object(reviews, "REVIEWS_DIR", root / "reviews"), \
                 patch.object(reviews, "CLEAN_DIR", root / "clean"), \
                 patch.object(reviews, "FINAL_DIR", root / "final"):
                rows = reviews.dashboard_rows()

        self.assertTrue(rows[0].event_review_ready)
        self.assertEqual(rows[0].missing_extraction_reviews, [])

    def test_dashboard_rows_do_not_count_final_summary_evidence_as_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clean").mkdir()
            final = root / "final"
            final.mkdir()
            (final / "session22_summary.md").write_text("final", encoding="utf-8")
            self.write_review(root, "session22", {
                "session": "session22",
                "status": "applied",
                "review_stage": "compose_final_summary",
                "final_summary": {
                    "session_title": "Session 22",
                    "real_world_date": "2026-05-31",
                    "in_world_date": "1832 AS - Namal 25",
                    "starting_location": "Catur",
                    "ending_location": "Catur",
                    "summary_markdown": "Canon summary with enough detail to satisfy validation while proving micro-event evidence does not count as pending work.",
                },
                "items": [
                    {"id": "event-001", "decision": "pending", "canonical_text": "Evidence only."},
                    {"id": "event-002", "decision": "pending", "canonical_text": "More evidence."},
                ],
            })

            with patch.object(reviews, "REVIEWS_DIR", root / "reviews"), \
                 patch.object(reviews, "CLEAN_DIR", root / "clean"), \
                 patch.object(reviews, "FINAL_DIR", final):
                rows = reviews.dashboard_rows()

        self.assertEqual(rows[0].pending_decisions, 0)
        self.assertEqual(rows[0].next_action, "done")

    def test_session_workspace_loads_selected_source_and_sorts_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            final = root / "final"
            reviews_dir = root / "reviews"
            clean.mkdir()
            final.mkdir()
            raw = root / "raw"
            raw.mkdir()
            (clean / "session03_diary.md").write_text("diary text", encoding="utf-8")
            (clean / "session03_summary.md").write_text("draft text", encoding="utf-8")
            (final / "session03_summary.md").write_text("final text", encoding="utf-8")
            (raw / "session03_transcript.txt").write_text("raw transcript text", encoding="utf-8")
            self.write_review(root, "session03", {
                "session": "session03",
                "status": "applied",
                "session_title": "Fey Woods",
                "items": [
                    {"id": "event-002", "sequence": 2, "decision": "accepted", "event_type": "travel", "applied_status": "applied"},
                    {"id": "event-001", "sequence": 1, "decision": "accepted", "event_type": "social", "applied_status": "applied"},
                ],
                "added_items": [
                    {"id": "added-001", "sequence": 1.5, "decision": "added", "canonical_text": "Added", "event_type": "social", "location": "Fey Woods", "significance": 3, "reason": "Important", "applied_status": "applied"},
                ],
            })

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch.object(reviews, "RAW_DIR", raw):
                workspace = reviews.session_workspace(3, source="final")
                transcript_workspace = reviews.session_workspace(3, source="transcript")

        self.assertEqual(workspace["source_label"], "Final Summary")
        self.assertEqual(workspace["source_text"], "final text")
        self.assertEqual(transcript_workspace["source_label"], "Raw Transcript")
        self.assertEqual(transcript_workspace["source_text"], "raw transcript text")
        self.assertEqual(workspace["source_view"], "raw")
        self.assertTrue(workspace["review_locked"])
        self.assertEqual([item["id"] for item in workspace["items"]], ["event-001", "added-001", "event-002"])
        self.assertIn("Starting location is required.", workspace["validation"])
        self.assertIn("Ending location is required.", workspace["validation"])

    def test_validate_review_document_reports_required_corrected_fields(self):
        notes = reviews.validate_review_document({
            "status": "reviewed",
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "corrected", "canonical_text": ""},
            ],
        })

        self.assertIn("Order 1 event event-001 is corrected but missing canonical_text.", notes)
        self.assertIn("Order 1 event event-001 has decision corrected but is missing a valid event type.", notes)

    def test_update_review_document_from_form_updates_existing_items(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "pending", "canonical_text": "", "event_type": "travel", "location": "Old", "significance": 2, "reason": "", "applied_status": "pending"},
            ],
            "added_items": [],
        }
        updated = reviews.update_review_document_from_form(document, {
            "item_id": ["event-001"],
            "section": ["items"],
            "sequence": ["1.5"],
            "decision": ["corrected"],
            "canonical_text": ["Canon text"],
            "event_type": ["social"],
            "location": ["Fey Woods"],
            "significance": ["4"],
            "reason": ["User corrected."],
        })

        item = updated["items"][0]
        self.assertEqual(item["sequence"], 1.5)
        self.assertEqual(item["decision"], "corrected")
        self.assertEqual(item["canonical_text"], "Canon text")
        self.assertEqual(item["event_type"], "social")
        self.assertEqual(item["location"], "Fey Woods")
        self.assertEqual(item["significance"], 4)
        self.assertEqual(item["reason"], "User corrected.")
        self.assertEqual(item["applied_status"], "pending")

    def test_update_review_document_from_form_marks_changed_applied_item_pending(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "accepted", "canonical_text": "", "event_type": "travel", "location": "Road", "significance": 2, "reason": "", "applied_status": "applied", "applied_on": "2026-05-05"},
            ],
            "added_items": [],
        }
        updated = reviews.update_review_document_from_form(document, {
            "item_id": ["event-001"],
            "section": ["items"],
            "sequence": ["1"],
            "decision": ["corrected"],
            "canonical_text": ["Corrected canon"],
            "event_type": ["travel"],
            "location": ["Road"],
            "significance": ["2"],
            "reason": [""],
        })

        item = updated["items"][0]
        self.assertEqual(item["applied_status"], "pending")
        self.assertEqual(item["applied_on"], "")

    def test_sorted_review_items_bubbles_pending_to_top(self):
        document = {
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "accepted"},
                {"id": "event-002", "sequence": 2, "decision": "pending"},
            ],
            "added_items": [
                {"id": "added-001", "sequence": 1.5, "decision": "corrected"},
            ],
        }

        items = reviews.sorted_review_items(document)

        self.assertEqual([item["id"] for item in items], ["event-002", "event-001", "added-001"])

    def test_update_single_review_item_only_changes_target(self):
        document = {
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "pending", "applied_status": "pending"},
                {"id": "event-002", "sequence": 2, "decision": "pending", "applied_status": "pending"},
            ],
            "added_items": [],
        }
        updated = reviews.update_single_review_item_from_form(document, {
            "item_id": ["event-001", "event-002"],
            "section": ["items", "items"],
            "sequence": ["1", "2"],
            "decision": ["accepted", "rejected"],
            "canonical_text": ["", ""],
            "event_type": ["travel", ""],
            "location": ["Road", ""],
            "significance": ["3", ""],
            "reason": ["", "Wrong"],
        }, "event-002")

        self.assertEqual(updated["items"][0]["decision"], "pending")
        self.assertEqual(updated["items"][1]["decision"], "rejected")
        self.assertEqual(updated["items"][1]["reason"], "Wrong")

    def test_update_batch_decision_updates_selected_items(self):
        document = {
            "items": [
                {"id": "event-001", "decision": "pending", "applied_status": "pending"},
                {"id": "event-002", "decision": "pending", "applied_status": "pending"},
            ],
            "added_items": [],
        }

        updated, errors = reviews.update_batch_decision(document, ["event-001"], "rejected", "Table talk.")

        self.assertEqual(errors, [])
        self.assertEqual(updated["items"][0]["decision"], "rejected")
        self.assertEqual(updated["items"][0]["reason"], "Table talk.")
        self.assertEqual(updated["items"][1]["decision"], "pending")

    def test_update_batch_decision_can_assign_bucket_without_decision(self):
        document = {
            "macro_events": [
                {"id": "macro-001", "order": 1, "description": "Plan", "location": "Western Coast"},
            ],
            "items": [
                {"id": "event-001", "decision": "pending", "applied_status": "pending"},
                {"id": "event-002", "decision": "pending", "applied_status": "pending"},
            ],
            "added_items": [],
        }

        updated, errors = reviews.update_batch_decision(document, ["event-001"], "", "", "macro-001")

        self.assertEqual(errors, [])
        self.assertEqual(updated["items"][0]["decision"], "pending")
        self.assertEqual(updated["items"][0]["macro_event_id"], "macro-001")
        self.assertEqual(updated["items"][0]["location"], "Western Coast")
        self.assertNotIn("macro_event_id", updated["items"][1])

    def test_update_review_document_inherits_bucket_location(self):
        document = {
            "macro_events": [
                {"id": "macro-001", "order": 1, "description": "Audience", "location": "Catur"},
            ],
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "pending", "location": "", "applied_status": "pending"},
            ],
            "added_items": [],
        }

        updated = reviews.update_review_document_from_form(document, {
            "item_id": ["event-001"],
            "section": ["items"],
            "sequence": ["1"],
            "decision": ["pending"],
            "canonical_text": [""],
            "event_type": [""],
            "location": [""],
            "significance": [""],
            "reason": [""],
            "macro_event_id": ["macro-001"],
        })

        self.assertEqual(updated["items"][0]["macro_event_id"], "macro-001")
        self.assertEqual(updated["items"][0]["location"], "Catur")

    def test_review_stage_defaults_to_high_level_order_but_preserves_applied(self):
        self.assertEqual(reviews.review_stage({"status": "in_review"}), "high_level_order")
        self.assertEqual(reviews.review_stage({"status": "in_review", "review_stage": "bucketing", "macro_events": [{"id": "macro-001"}]}), "bucketing")
        self.assertEqual(reviews.review_stage({"status": "in_review", "review_stage": "bucketing", "items": [{"id": "event-001"}]}), "high_level_order")
        self.assertEqual(reviews.review_stage({"status": "applied"}), "event_resolution")

    def test_update_bucketing_from_form_assigns_bucket_or_rejects(self):
        document = {
            "macro_events": [
                {"id": "macro-001", "order": 1, "description": "Plan", "location": "Western Coast"},
            ],
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "pending", "location": "Old", "applied_status": "pending"},
                {"id": "event-002", "sequence": 2, "decision": "pending", "location": "Old", "applied_status": "pending"},
            ],
            "added_items": [],
        }

        updated = reviews.update_bucketing_from_form(document, {
            "bucket_item_id": ["event-001", "event-002"],
            "bucket_section": ["items", "items"],
            "bucket_macro_event_id": ["macro-001", ""],
            "bucket_action": ["", "rejected"],
            "review_stage": ["event_resolution"],
        })

        self.assertEqual(updated["review_stage"], "event_resolution")
        self.assertEqual(updated["items"][0]["macro_event_id"], "macro-001")
        self.assertEqual(updated["items"][0]["location"], "Western Coast")
        self.assertEqual(updated["items"][1]["decision"], "rejected")

    def test_filtered_review_items_supports_bucket_workflow(self):
        items = [
            {"id": "event-001", "macro_event_id": "macro-001", "decision": "pending"},
            {"id": "event-002", "decision": "pending"},
            {"id": "event-003", "macro_event_id": "macro-001", "decision": "rejected"},
        ]

        self.assertEqual([item["id"] for item in reviews.filtered_review_items(items, "macro-001")], ["event-001", "event-003"])
        self.assertEqual([item["id"] for item in reviews.filtered_review_items(items, "unbucketed")], ["event-002"])
        self.assertEqual([item["id"] for item in reviews.filtered_review_items(items, "rejected")], ["event-003"])

    def test_update_macro_events_from_form_adds_and_removes_buckets(self):
        document = {
            "macro_events": [
                {"id": "macro-001", "order": 1, "description": "Old", "location": "Road"},
                {"id": "macro-002", "order": 2, "description": "Remove me", "location": "Boat"},
            ],
            "items": [
                {"id": "event-001", "macro_event_id": "macro-002"},
            ],
            "added_items": [],
        }

        updated = reviews.update_macro_events_from_form(document, {
            "macro_id": ["macro-001", "macro-002"],
            "macro_order": ["1", "2"],
            "macro_description": ["Party makes a plan", "Remove me"],
            "macro_location": ["Western Coast", "Boat"],
            "remove_macro_id": ["macro-002"],
            "new_macro_order": ["3"],
            "new_macro_description": ["Party dives to Catur"],
            "new_macro_location": ["Underwater"],
        })

        self.assertEqual([item["id"] for item in updated["macro_events"]], ["macro-001", "macro-003"])
        self.assertEqual([item["order"] for item in updated["macro_events"]], [1, 2])
        self.assertEqual(updated["macro_events"][0]["description"], "Party makes a plan")
        self.assertEqual(updated["macro_events"][1]["description"], "Party dives to Catur")
        self.assertNotIn("macro_event_id", updated["items"][0])

    def test_macro_locations_to_validate_ignores_removed_bucket_location(self):
        locations = macro_locations_to_validate({
            "macro_id": ["macro-001", "macro-002"],
            "macro_location": ["Road", "Unknown Removed Place"],
            "remove_macro_id": ["macro-002"],
            "new_macro_location": ["New Place"],
        })

        self.assertEqual(locations, ["Road", "New Place"])

    def test_update_macro_events_from_form_deduplicates_modal_and_page_rows(self):
        document = {
            "macro_events": [
                {"id": "macro-001", "order": 1, "description": "Keep", "location": "Road"},
                {"id": "macro-002", "order": 2, "description": "Remove me", "location": "Boat"},
            ],
            "items": [
                {"id": "event-001", "macro_event_id": "macro-002"},
            ],
            "added_items": [],
        }

        updated = reviews.update_macro_events_from_form(document, {
            "macro_id": ["macro-001", "macro-002", "macro-001", "macro-002"],
            "macro_order": ["1", "2", "1", "2"],
            "macro_description": ["Keep", "Remove me", "Keep", "Remove me"],
            "macro_location": ["Road", "Boat", "Road", "Boat"],
            "remove_macro_id": ["macro-002"],
        })

        self.assertEqual([item["id"] for item in updated["macro_events"]], ["macro-001"])
        self.assertEqual(updated["macro_events"][0]["description"], "Keep")
        self.assertNotIn("macro_event_id", updated["items"][0])

    def test_update_macro_events_from_form_delete_without_rows_preserves_other_buckets(self):
        document = {
            "macro_events": [
                {"id": "macro-001", "order": 1, "description": "Keep", "location": "Road"},
                {"id": "macro-002", "order": 2, "description": "Remove me", "location": "Boat"},
            ],
            "items": [
                {"id": "event-001", "macro_event_id": "macro-002"},
            ],
            "added_items": [],
        }

        updated = reviews.update_macro_events_from_form(document, {
            "remove_macro_id": ["macro-002"],
        })

        self.assertEqual([item["id"] for item in updated["macro_events"]], ["macro-001"])
        self.assertEqual(updated["macro_events"][0]["description"], "Keep")
        self.assertNotIn("macro_event_id", updated["items"][0])

    def test_update_macro_events_from_form_renumbers_decimal_insertions(self):
        document = {
            "macro_events": [
                {"id": "macro-001", "order": 1, "description": "First", "location": "Road"},
                {"id": "macro-002", "order": 2, "description": "Second", "location": "Boat"},
            ],
            "items": [],
            "added_items": [],
        }

        updated = reviews.update_macro_events_from_form(document, {
            "macro_id": ["macro-001", "macro-002"],
            "macro_order": ["1", "2"],
            "macro_description": ["First", "Second"],
            "macro_location": ["Road", "Boat"],
            "new_macro_order": ["1.5"],
            "new_macro_description": ["Between"],
            "new_macro_location": ["Underwater"],
        })

        self.assertEqual([item["description"] for item in updated["macro_events"]], ["First", "Between", "Second"])
        self.assertEqual([item["order"] for item in updated["macro_events"]], [1, 2, 3])

    def test_apply_macro_event_order_assigns_locations_and_contiguous_sequences(self):
        document = {
            "macro_events": [
                {"id": "macro-002", "order": 2, "description": "Boat", "location": "Boat"},
                {"id": "macro-001", "order": 1, "description": "Plan", "location": "Western Coast"},
            ],
            "items": [
                {"id": "event-001", "sequence": 10, "macro_event_id": "macro-001", "location": ""},
                {"id": "event-002", "sequence": 3, "macro_event_id": "macro-002", "location": ""},
                {"id": "event-003", "sequence": 2, "macro_event_id": "macro-001", "location": ""},
            ],
            "added_items": [],
        }

        updated, errors = reviews.apply_macro_event_order(document)

        self.assertEqual(errors, [])
        by_id = {item["id"]: item for item in updated["items"]}
        self.assertEqual(by_id["event-003"]["sequence"], 1)
        self.assertEqual(by_id["event-001"]["sequence"], 2)
        self.assertEqual(by_id["event-002"]["sequence"], 3)
        self.assertEqual(by_id["event-001"]["location"], "Western Coast")
        self.assertEqual(by_id["event-002"]["location"], "Boat")

    def test_merge_review_items_adds_merged_item_and_rejects_originals(self):
        document = {
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "pending", "source_text": "Fragment one.", "event_type": "social", "location": "Catur", "significance": 2, "applied_status": "pending"},
                {"id": "event-002", "sequence": 2, "decision": "pending", "source_text": "Fragment two.", "event_type": "social", "location": "Catur", "significance": 4, "applied_status": "pending"},
            ],
            "added_items": [],
        }

        updated, errors = reviews.merge_review_items(document, ["event-001", "event-002"], {
            "canonical_text": "One coherent event.",
            "event_type": "social",
            "location": "Catur",
            "significance": "4",
            "reason": "Same conversation.",
        }, merged_on="2026-05-18")

        self.assertEqual(errors, [])
        self.assertEqual(updated["items"][0]["decision"], "rejected")
        self.assertEqual(updated["items"][0]["reason"], "Merged into added-001.")
        self.assertEqual(updated["items"][1]["decision"], "rejected")
        self.assertEqual(updated["added_items"][0]["id"], "added-001")
        self.assertEqual(updated["added_items"][0]["canonical_text"], "One coherent event.")
        self.assertEqual(updated["added_items"][0]["decision"], "added")

    def test_add_review_item_appends_valid_added_item(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [],
            "added_items": [
                {"id": "added-001", "decision": "added"},
            ],
        }
        updated, errors = reviews.add_review_item(document, {
            "sequence": "2.5",
            "canonical_text": "The party learned a missing truth.",
            "event_type": "discovery",
            "location": "Bentrios",
            "significance": "4",
            "reason": "Missing from draft.",
        }, added_on="2026-05-06")

        self.assertEqual(errors, [])
        item = updated["added_items"][1]
        self.assertEqual(item["id"], "added-002")
        self.assertEqual(item["sequence"], 2.5)
        self.assertEqual(item["source_type"], "user_added")
        self.assertEqual(item["decision"], "added")
        self.assertEqual(item["canonical_text"], "The party learned a missing truth.")
        self.assertEqual(item["event_type"], "discovery")
        self.assertEqual(item["location"], "Bentrios")
        self.assertEqual(item["significance"], 4)
        self.assertEqual(item["reason"], "Missing from draft.")
        self.assertEqual(item["decided_by"], "user")
        self.assertEqual(item["decided_on"], "2026-05-06")
        self.assertEqual(item["applied_status"], "pending")

    def test_add_review_item_reports_missing_required_fields(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [],
            "added_items": [],
        }
        updated, errors = reviews.add_review_item(document, {
            "sequence": "",
            "canonical_text": "",
            "event_type": "social",
            "location": "",
            "significance": "",
            "reason": "",
        })

        self.assertIs(updated, document)
        self.assertIn("Added item is missing sequence.", errors)
        self.assertIn("Added item is missing canonical_text.", errors)
        self.assertIn("Added item is missing location.", errors)

    def test_unknown_locations_compares_case_insensitively_and_dedupes(self):
        unknown = reviews.unknown_locations(
            ["Bentrios", "bentrios", "New Place", "new place", "", "Catur"],
            ["Bentrios", "Catur"],
        )

        self.assertEqual(unknown, ["New Place"])

    def test_remove_added_item_removes_only_matching_added_item(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [
                {"id": "event-001", "decision": "accepted"},
            ],
            "added_items": [
                {"id": "added-001", "decision": "added"},
                {"id": "added-002", "decision": "added"},
            ],
        }
        updated, errors = reviews.remove_added_item(document, "added-001")

        self.assertEqual(errors, [])
        self.assertEqual([item["id"] for item in updated["items"]], ["event-001"])
        self.assertEqual([item["id"] for item in updated["added_items"]], ["added-002"])

    def test_remove_added_item_reports_missing_item(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [
                {"id": "event-001", "decision": "accepted"},
            ],
            "added_items": [],
        }
        updated, errors = reviews.remove_added_item(document, "event-001")

        self.assertIs(updated, document)
        self.assertEqual(errors, ["Added item not found: event-001."])

    def test_reopen_review_document_unlocks_without_dirtying_items(self):
        document = {
            "session": "session01",
            "status": "applied",
            "applied_on": "2026-05-05",
            "items": [
                {"id": "event-001", "decision": "accepted", "applied_status": "applied", "applied_on": "2026-05-05"},
            ],
            "added_items": [],
        }
        updated = reviews.reopen_review_document(document, reopened_on="2026-05-06")

        self.assertEqual(updated["status"], "in_review")
        self.assertEqual(updated["reopened_on"], "2026-05-06")
        self.assertEqual(updated["items"][0]["applied_status"], "applied")

    def test_mark_reviewed_document_requires_no_pending_decisions(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [
                {"id": "event-001", "decision": "pending"},
            ],
            "added_items": [],
        }
        updated, errors = reviews.mark_reviewed_document(document, reviewed_on="2026-05-06")

        self.assertIs(updated, document)
        self.assertEqual(updated["status"], "in_review")
        self.assertIn("1 review item(s) still have pending decisions.", errors)

    def test_mark_reviewed_document_sets_status_when_ready(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "accepted", "event_type": "travel"},
            ],
            "added_items": [],
        }
        updated, errors = reviews.mark_reviewed_document(document, reviewed_on="2026-05-06")

        self.assertEqual(errors, [])
        self.assertEqual(updated["status"], "reviewed")
        self.assertEqual(updated["reviewed_on"], "2026-05-06")

    def test_final_summary_review_does_not_require_micro_event_decisions(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "review_stage": "compose_final_summary",
            "final_summary": {
                "session_title": "Session 01",
                "real_world_date": "2026-05-25",
                "in_world_date": "N/A",
                "starting_location": "Road",
                "ending_location": "Village",
                "summary_markdown": "The party travels from the road to the village and establishes the core conflict for the session.",
            },
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "pending"},
            ],
            "added_items": [],
        }

        updated, errors = reviews.mark_reviewed_document(document, reviewed_on="2026-05-06")

        self.assertEqual(errors, [])
        self.assertEqual(updated["status"], "reviewed")

    def test_final_summary_review_requires_timeline_fields(self):
        document = {
            "session": "session01",
            "status": "in_review",
            "review_stage": "compose_final_summary",
            "final_summary": {
                "session_title": "Session 01",
                "real_world_date": "2026-05-25",
                "in_world_date": "N/A",
                "starting_location": "",
                "ending_location": "Village",
                "summary_markdown": "The party travels from the road to the village and establishes the core conflict for the session.",
            },
            "items": [],
            "added_items": [],
        }

        updated, errors = reviews.mark_reviewed_document(document, reviewed_on="2026-05-06")

        self.assertIs(updated, document)
        self.assertIn("Starting location is required.", errors)


    def test_render_markdown_interprets_headings_and_emphasis(self):
        html = reviews.render_markdown("# Title\n\nA **bold** line")
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("<strong>bold</strong>", html)


class WebReviewAppTest(unittest.TestCase):
    def test_dashboard_renders_current_app_version(self):
        with patch.object(reviews, "dashboard_rows", return_value=[]):
            client = TestClient(app)
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"Farrlind Campaign {app_version()}", response.text)

    def test_dashboard_renders_git_hash_when_available(self):
        with patch.object(reviews, "dashboard_rows", return_value=[]), \
             patch.dict(os.environ, {"FARRLIND_GIT_HASH": "baa1b3450a894891cc86a82760aef21c4ac3dafa"}):
            client = TestClient(app)
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"Farrlind Campaign {app_version()} · {app_git_hash_short()}", response.text)

    def test_dashboard_renders_world_map_modal_link(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(reviews, "dashboard_rows", return_value=[]), \
             patch("web_review.app.assets_dir", return_value=Path(tmp)):
            (Path(tmp) / "world-map.png").write_bytes(b"map")
            client = TestClient(app)
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="#world-map-modal"', response.text)
        self.assertIn("World Map", response.text)
        self.assertIn("/world-map/image?v=", response.text)
        self.assertIn("Farrlind World Map", response.text)

    def test_dashboard_renders_world_map_placeholder_without_campaign_map(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(reviews, "dashboard_rows", return_value=[]), \
             patch("web_review.app.assets_dir", return_value=Path(tmp)):
            client = TestClient(app)
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("No Map Uploaded", response.text)
        self.assertIn("Upload Map Image", response.text)
        self.assertNotIn("/static/farrlind-world-map.png", response.text)

    def test_world_map_image_returns_campaign_asset(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("web_review.app.assets_dir", return_value=Path(tmp)):
            (Path(tmp) / "world-map.png").write_bytes(b"map")
            client = TestClient(app)
            response = client.get("/world-map/image")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"map")
        self.assertEqual(response.headers["content-type"], "image/png")

    def test_world_map_upload_replaces_existing_campaign_asset(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("web_review.app.assets_dir", return_value=Path(tmp)):
            assets = Path(tmp)
            (assets / "world-map.png").write_bytes(b"old")
            client = TestClient(app)
            response = client.post(
                "/world-map",
                files={"map_image": ("new-map.jpg", b"new", "image/jpeg")},
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/#world-map-modal")
            self.assertFalse((assets / "world-map.png").exists())
            self.assertEqual((assets / "world-map.jpg").read_bytes(), b"new")

    def test_final_summary_composer_shows_micro_events_without_buckets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            reviews_dir.mkdir()
            clean.mkdir()
            final.mkdir()
            (reviews_dir / "session01_review.yaml").write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [
                    {"id": "event-001", "sequence": 1, "source_text": "The party reaches the inn.", "location": "Night Lotus"},
                    {"id": "event-002", "sequence": 2, "source_text": "A stranger enters.", "location": "Night Lotus"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.app.reviews.event_review_access_blocked", return_value=False), \
                 patch("web_review.app.canon_location_names", return_value=[]), \
                 patch("web_review.services.canon.location_types", return_value=[]):
                client = TestClient(app)
                response = client.get("/sessions/session01/review")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Compose Final Summary", response.text)
        self.assertIn("Micro Events", response.text)
        self.assertIn("The party reaches the inn.", response.text)
        self.assertIn("A stranger enters.", response.text)
        self.assertIn("2 draft", response.text)
        self.assertNotIn("High-Level Event Order", response.text)

    def test_event_review_dashboard_disables_blocked_sessions(self):
        row = reviews.ReviewSummary(
            session="session01",
            session_number=1,
            status="in_review",
            title="Start",
            path="/tmp/session01_review.yaml",
            review_exists=True,
            final_exists=False,
            total_items=1,
            base_items=1,
            added_items=0,
            pending_decisions=1,
            accepted=0,
            rejected=0,
            corrected=0,
            added=0,
            unknown_decisions=0,
            unapplied_items=0,
            next_action="edit",
            event_review_ready=False,
            missing_extraction_reviews=["NPC Extraction"],
        )
        with patch.object(reviews, "dashboard_rows", return_value=[row]):
            client = TestClient(app)
            response = client.get("/event-review")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Session Review", response.text)
        self.assertIn("Waiting", response.text)
        self.assertIn("Missing extraction reviews: NPC Extraction", response.text)

    def test_event_review_dashboard_opens_ready_sessions(self):
        row = reviews.ReviewSummary(
            session="session01",
            session_number=1,
            status="in_review",
            title="Start",
            path="/tmp/session01_review.yaml",
            review_exists=True,
            final_exists=False,
            total_items=1,
            base_items=1,
            added_items=0,
            pending_decisions=1,
            accepted=0,
            rejected=0,
            corrected=0,
            added=0,
            unknown_decisions=0,
            unapplied_items=0,
            next_action="edit",
            event_review_ready=True,
            missing_extraction_reviews=[],
        )
        with patch.object(reviews, "dashboard_rows", return_value=[row]):
            client = TestClient(app)
            response = client.get("/event-review")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/sessions/session01/review"', response.text)

    def test_print_view_keeps_final_summary_composer(self):
        client = TestClient(app)
        response = client.get("/sessions/session20/review?source=final&view=print")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Compose Final Summary", response.text)
        self.assertIn("Canon Final Summary", response.text)

    def test_session_review_renders_command_result(self):
        COMMAND_RESULTS["abc"] = {
            "action": "Apply to Database",
            "returncode": 1,
            "stdout": "some output",
            "stderr": "some error",
            "ok": False,
        }
        try:
            client = TestClient(app)
            response = client.get("/sessions/session20/review?source=final&view=raw&command_result=abc")
        finally:
            COMMAND_RESULTS.pop("abc", None)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Apply to Database", response.text)
        self.assertIn("some output", response.text)
        self.assertIn("some error", response.text)

    def test_raw_view_preserves_source_markdown(self):
        client = TestClient(app)
        response = client.get("/sessions/session20/review?source=final&view=raw")

        self.assertEqual(response.status_code, 200)
        self.assertIn("source-text", response.text)

    def test_final_summary_review_ignores_stale_macro_modal_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            reviews_dir.mkdir()
            clean.mkdir()
            final.mkdir()
            (reviews_dir / "session01_review.yaml").write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "review_stage": "compose_final_summary",
                "final_summary": {
                    "session_title": "Session 01",
                    "real_world_date": "2026-05-25",
                    "in_world_date": "N/A",
                    "starting_location": "Road",
                    "ending_location": "Village",
                    "summary_markdown": "The party travels from the road to the village and establishes the core conflict for the session.",
                },
                "macro_events": [{"id": "macro-001", "order": 1, "description": "Old Bucket", "location": "Road"}],
                "items": [{"id": "event-001", "sequence": 1, "decision": "pending", "source_text": "Micro event text."}],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch.object(reviews, "event_review_access_blocked", return_value=False), \
                 patch("web_review.services.canon.locations", return_value=["Road", "Village"]), \
                 patch("web_review.services.canon.location_types", return_value=[]):
                client = TestClient(app)
                response = client.get("/sessions/session01/review?macro_modal=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Compose Final Summary", response.text)
        self.assertIn("Micro event text.", response.text)
        self.assertNotIn("High-Level Event Order", response.text)

    def test_final_summary_review_macro_post_does_not_change_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            reviews_dir.mkdir()
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "review_stage": "compose_final_summary",
                "final_summary": {
                    "session_title": "Session 01",
                    "real_world_date": "2026-05-25",
                    "in_world_date": "N/A",
                    "starting_location": "Road",
                    "ending_location": "Village",
                    "summary_markdown": "The party travels from the road to the village and establishes the core conflict for the session.",
                },
                "macro_events": [{"id": "macro-001", "order": 1, "description": "Old Bucket", "location": "Road"}],
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/macros", data={
                    "source": "narrative",
                    "view": "raw",
                    "review_stage": "bucketing",
                    "remove_macro_id": "macro-001",
                }, follow_redirects=False)
                saved = yaml.safe_load(path.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 303)
        self.assertEqual(saved["review_stage"], "compose_final_summary")
        self.assertEqual(saved["macro_events"][0]["id"], "macro-001")

    def test_session_review_blocks_until_extraction_reviews_complete(self):
        with patch.object(reviews, "event_review_access_blocked", return_value=True), \
             patch.object(reviews, "missing_extraction_reviews", return_value=["NPC Extraction"]), \
             patch.object(reviews, "session_workspace", return_value={
                 "session_key": "session01",
                 "document": {},
                 "summary": None,
                 "source": "diary",
                 "source_view": "raw",
                 "source_text": "",
                 "source_html": "",
                 "source_label": "Diary",
                 "items": [],
                 "selected_bucket": "",
                 "review_locked": False,
                 "review_stage": "event_resolution",
                 "macro_events": [],
                 "bucket_counts": {},
                 "validation": [],
             }):
            client = TestClient(app)
            response = client.get("/sessions/session01/review")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Event review is not available yet.", response.text)
        self.assertIn("NPC Extraction", response.text)

    def test_session_review_missing_yaml_can_initialize_from_web(self):
        with patch.object(reviews, "event_review_access_blocked", return_value=False), \
             patch.object(reviews, "session_workspace", return_value={
                 "session_key": "session01",
                 "document": {},
                 "summary": None,
                 "source": "diary",
                 "source_view": "raw",
                 "source_text": "",
                 "source_html": "",
                 "source_label": "Diary",
                 "items": [],
                 "selected_bucket": "",
                 "review_locked": False,
                 "review_stage": "event_resolution",
                 "macro_events": [],
                 "bucket_counts": {},
                 "validation": [],
             }):
            client = TestClient(app)
            response = client.get("/sessions/session01/review")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Initialize Event Review", response.text)

    def test_init_session_review_runs_command_when_ready(self):
        result = commands.CommandResult(0, "created", "")
        with patch.object(reviews, "event_review_access_blocked", return_value=False), \
             patch("web_review.services.commands.init_review", return_value=result):
            client = TestClient(app)
            response = client.post("/sessions/session01/review/init", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("init_reviewed=1", response.headers["location"])

    def test_init_session_review_redirects_when_blocked(self):
        with patch.object(reviews, "event_review_access_blocked", return_value=True):
            client = TestClient(app)
            response = client.post("/sessions/session01/review/init", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("event_review_blocked=1", response.headers["location"])

    def test_archive_session_review_is_print_only_reader(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/sessions/session20/review?source=final&view=raw")

        self.assertEqual(response.status_code, 200)
        self.assertIn("session20 Archive", response.text)
        self.assertIn("source-rendered", response.text)
        self.assertIn("Archive source selector", response.text)
        self.assertIn("Diary</a>", response.text)
        self.assertIn("Summary</a>", response.text)
        self.assertNotIn("source-text", response.text)
        self.assertNotIn("Draft Summary", response.text)
        self.assertNotIn("Final Summary", response.text)
        self.assertNotIn("Source</a>", response.text)
        self.assertNotIn("Print</a>", response.text)
        self.assertNotIn("Save Review", response.text)
        self.assertNotIn("Reopen Review", response.text)
        self.assertNotIn("Add Item", response.text)

    def test_save_review_route_writes_yaml_and_redirects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = root / "reviews" / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "session_title": "Start",
                "items": [
                    {"id": "event-001", "sequence": 1, "decision": "pending", "canonical_text": "", "event_type": "travel", "location": "Road", "significance": 2, "reason": "", "applied_status": "pending"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.canon.locations", return_value=[]):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/save", data={
                    "source": "diary",
                    "view": "print",
                    "item_id": "event-001",
                    "section": "items",
                    "sequence": "2",
                    "decision": "accepted",
                    "canonical_text": "Accepted canon",
                    "event_type": "social",
                    "location": "Fey Woods",
                    "significance": "3",
                    "reason": "Looks right.",
                    "confirm_new_locations": "1",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            item = saved["items"][0]
            self.assertEqual(item["sequence"], 2)
            self.assertEqual(item["decision"], "accepted")
            self.assertEqual(item["canonical_text"], "Accepted canon")
            self.assertEqual(item["event_type"], "social")
            self.assertEqual(item["location"], "Fey Woods")
            self.assertEqual(item["significance"], 3)
            self.assertEqual(item["reason"], "Looks right.")

    def test_save_review_route_allows_unknown_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [
                    {"id": "event-001", "sequence": 1, "decision": "pending", "location": "Bentrios", "applied_status": "pending"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.canon.locations", return_value=["Bentrios"]):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/save", data={
                    "source": "diary",
                    "view": "raw",
                    "item_id": "event-001",
                    "section": "items",
                    "sequence": "1",
                    "decision": "accepted",
                    "canonical_text": "",
                    "event_type": "travel",
                    "location": "New Place",
                    "significance": "2",
                    "reason": "",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("saved=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["location"], "New Place")

    def test_macro_routes_save_and_apply_bucket_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session21_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session21",
                "status": "in_review",
                "macro_events": [],
                "items": [
                    {"id": "event-001", "sequence": 10, "decision": "pending", "location": "", "applied_status": "pending"},
                    {"id": "event-002", "sequence": 20, "decision": "pending", "location": "", "applied_status": "pending"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.canon.locations", return_value=["Western Coast", "Boat"]), \
                 patch("web_review.services.canon.create_location") as create_location:
                client = TestClient(app)
                response = client.post("/sessions/session21/review/macros", data={
                    "source": "diary",
                    "view": "raw",
                    "new_macro_order": "1",
                    "new_macro_description": "Party discusses plan",
                    "new_macro_location": "Western Coast",
                }, follow_redirects=False)
                self.assertEqual(response.status_code, 303)
                self.assertIn("macro_modal=1", response.headers["location"])
                create_location.assert_not_called()
                saved = yaml.safe_load(path.read_text(encoding="utf-8"))
                macro_id = saved["macro_events"][0]["id"]
                response = client.post("/sessions/session21/review/apply-macros", data={
                    "source": "diary",
                    "view": "raw",
                    "item_id": ["event-001", "event-002"],
                    "section": ["items", "items"],
                    "sequence": ["10", "20"],
                    "decision": ["pending", "pending"],
                    "canonical_text": ["", ""],
                    "event_type": ["", ""],
                    "location": ["", ""],
                    "significance": ["", ""],
                    "reason": ["", ""],
                    "macro_event_id": [macro_id, macro_id],
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("macros_applied=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["sequence"], 1)
            self.assertEqual(saved["items"][1]["sequence"], 2)
            self.assertEqual(saved["items"][0]["location"], "Western Coast")

    def test_macro_route_auto_creates_unknown_bucket_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session21_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session21",
                "status": "in_review",
                "macro_events": [],
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.canon.locations", return_value=[]), \
                 patch("web_review.services.canon.create_location") as create_location:
                client = TestClient(app)
                response = client.post("/sessions/session21/review/macros", data={
                    "source": "diary",
                    "view": "raw",
                    "new_macro_order": "1",
                    "new_macro_description": "Party discusses plan",
                    "new_macro_location": "Western Coast of Farrlind",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("macros_saved=1", response.headers["location"])
            create_location.assert_called_once()
            values = create_location.call_args.args[0]
            self.assertEqual(values["name"], "Western Coast of Farrlind")
            self.assertEqual(values["first_visited_session"], 21)
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["macro_events"][0]["location"], "Western Coast of Farrlind")

    def test_macro_route_delete_bucket_ignores_removed_unknown_location_and_redirects_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session21_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session21",
                "status": "in_review",
                "macro_events": [
                    {"id": "macro-001", "order": 1, "description": "Keep", "location": "Road"},
                    {"id": "macro-002", "order": 2, "description": "Remove", "location": "Unknown Removed Place"},
                ],
                "items": [
                    {"id": "event-001", "sequence": 1, "macro_event_id": "macro-002", "decision": "pending"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.canon.locations", return_value=["Road"]), \
                 patch("web_review.services.canon.create_location") as create_location:
                client = TestClient(app)
                response = client.post("/sessions/session21/review/macros", data={
                    "source": "diary",
                    "view": "raw",
                    "bucket": "macro-002",
                    "macro_id": ["macro-001", "macro-002"],
                    "macro_order": ["1", "2"],
                    "macro_description": ["Keep", "Remove"],
                    "macro_location": ["Road", "Unknown Removed Place"],
                    "remove_macro_id": "macro-002",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("macros_saved=1", response.headers["location"])
            self.assertIn("bucket=all", response.headers["location"])
            create_location.assert_not_called()
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual([macro["id"] for macro in saved["macro_events"]], ["macro-001"])
            self.assertNotIn("macro_event_id", saved["items"][0])

    def test_save_review_route_rejects_applied_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "applied",
                "items": [
                    {"id": "event-001", "sequence": 1, "decision": "accepted", "applied_status": "applied"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/save", data={
                    "item_id": "event-001",
                    "section": "items",
                    "sequence": "1",
                    "decision": "accepted",
                })

        self.assertEqual(response.status_code, 409)

    def test_reopen_review_route_writes_unlocked_yaml_and_redirects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "applied",
                "items": [
                    {"id": "event-001", "sequence": 1, "decision": "accepted", "applied_status": "applied"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/reopen", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("reopened=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "in_review")
            self.assertEqual(saved["items"][0]["applied_status"], "applied")

    def test_mark_reviewed_route_saves_form_and_marks_ready_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [
                    {"id": "event-001", "sequence": 1, "decision": "pending", "canonical_text": "", "event_type": "travel", "location": "Road", "significance": 2, "reason": "", "applied_status": "pending"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.workflow.sync_session_workflow") as sync:
                client = TestClient(app)
                response = client.post("/sessions/session01/review/mark-reviewed", data={
                    "source": "diary",
                    "view": "raw",
                    "item_id": "event-001",
                    "section": "items",
                    "sequence": "1",
                    "decision": "accepted",
                    "canonical_text": "",
                    "event_type": "travel",
                    "location": "Road",
                    "significance": "2",
                    "reason": "",
                    "confirm_new_locations": "1",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("marked=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "reviewed")
            self.assertEqual(saved["items"][0]["decision"], "accepted")
            sync.assert_called_once_with(1)

    def test_mark_reviewed_route_saves_but_does_not_mark_invalid_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [
                    {"id": "event-001", "sequence": 1, "decision": "pending", "applied_status": "pending"},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/mark-reviewed", data={
                    "source": "diary",
                    "view": "raw",
                    "item_id": "event-001",
                    "section": "items",
                    "sequence": "1",
                    "decision": "pending",
                    "canonical_text": "",
                    "event_type": "",
                    "location": "",
                    "significance": "",
                    "reason": "",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("mark_failed=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "in_review")
            self.assertEqual(saved["items"][0]["decision"], "pending")

    def test_add_item_route_appends_added_item_and_redirects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/add-item", data={
                    "source": "diary",
                    "view": "raw",
                    "new_sequence": "3.5",
                    "new_canonical_text": "The party added a missing event.",
                    "new_event_type": "social",
                    "new_location": "Bentrios",
                    "new_significance": "3",
                    "new_reason": "User remembered it.",
                    "confirm_new_locations": "1",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("item_added=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["added_items"][0]["id"], "added-001")
            self.assertEqual(saved["added_items"][0]["canonical_text"], "The party added a missing event.")

    def test_add_item_route_allows_unknown_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.canon.locations", return_value=["Bentrios"]):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/add-item", data={
                    "source": "diary",
                    "view": "raw",
                    "new_sequence": "2",
                    "new_canonical_text": "The party found somewhere new.",
                    "new_event_type": "discovery",
                    "new_location": "New Place",
                    "new_significance": "3",
                    "new_reason": "New canon location.",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("item_added=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["added_items"][0]["location"], "New Place")

    def test_add_item_route_does_not_save_invalid_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/add-item", data={
                    "source": "diary",
                    "view": "raw",
                    "new_sequence": "",
                    "new_canonical_text": "",
                    "new_event_type": "social",
                    "new_location": "",
                    "new_significance": "",
                    "new_reason": "",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("item_add_failed=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["added_items"], [])

    def test_remove_added_item_route_removes_item_and_redirects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [],
                "added_items": [
                    {"id": "added-001", "decision": "added"},
                    {"id": "added-002", "decision": "added"},
                ],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/remove-added-item", data={
                    "source": "diary",
                    "view": "raw",
                    "remove_item_id": "added-001",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            self.assertIn("item_removed=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in saved["added_items"]], ["added-002"])

    def test_remove_added_item_route_rejects_applied_review_until_reopened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "applied",
                "items": [],
                "added_items": [
                    {"id": "added-001", "decision": "added", "applied_status": "applied"},
                ],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/remove-added-item", data={
                    "source": "diary",
                    "view": "raw",
                    "remove_item_id": "added-001",
                })

        self.assertEqual(response.status_code, 409)

    def test_remove_added_item_route_allows_reopened_applied_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "reopened_on": "2026-05-06",
                "items": [],
                "added_items": [
                    {"id": "added-001", "decision": "added", "applied_status": "applied"},
                ],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/remove-added-item", data={
                    "source": "diary",
                    "view": "raw",
                    "remove_item_id": "added-001",
                }, follow_redirects=False)

            self.assertEqual(response.status_code, 303)
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["added_items"], [])


class CanonServiceTest(unittest.TestCase):
    def test_timeline_in_game_date_display_collapses_multiple_dates_to_bounds(self):
        self.assertEqual(
            canon.timeline_in_game_date_display(
                "1832 AS Namal 13, 1832 AS Namal 14, 1832 AS Namal 15-17, 1832 AS Namal 18"
            ),
            "1832 AS Namal 13 thru 1832 AS Namal 18",
        )
        self.assertEqual(
            canon.timeline_in_game_date_display(
                "1832 AS Apollal 21, 1832 AS Namal 1, 1832 AS Namal 4, 1832 AS Namal 6"
            ),
            "1832 AS Apollal 21 thru 1832 AS Namal 6",
        )
        self.assertEqual(
            canon.timeline_in_game_date_display("1832 AS Namal 19 (continued)"),
            "1832 AS Namal 19",
        )

    def test_locations_returns_ordered_names_from_db_rows(self):
        with patch("web_review.db.fetch_all", return_value=[{"name": "Balrog"}, {"name": "Catur"}]) as fetch:
            self.assertEqual(canon.locations(), ["Balrog", "Catur"])
        self.assertIn("FROM location", fetch.call_args.args[0])

    def test_location_rows_returns_full_location_ledger(self):
        rows = [{
            "id": 1,
            "name": "Bentrios",
            "location_type": "city",
            "parent_location": None,
            "description": "Starting city",
            "is_underwater": False,
            "is_feywild": False,
            "first_visited_session": 0,
            "notes": "",
        }]
        with patch("web_review.db.fetch_all", return_value=rows) as fetch:
            self.assertEqual(canon.location_rows(), rows)
        self.assertIn("LEFT JOIN location_type", fetch.call_args.args[0])

    def test_location_crud_services_run_expected_statements(self):
        values = {
            "name": "New Place",
            "location_type_id": 1,
            "parent_location_id": None,
            "description": "A new place.",
            "is_underwater": False,
            "is_feywild": False,
            "first_visited_session": None,
            "notes": "",
        }
        with patch("web_review.db.execute") as execute:
            canon.create_location(values)
            canon.update_location(12, values)
            canon.delete_location(12)

        self.assertIn("INSERT INTO location", execute.call_args_list[0].args[0])
        self.assertIn("UPDATE location", execute.call_args_list[1].args[0])
        self.assertIn("DELETE FROM location", execute.call_args_list[2].args[0])

    def test_npc_rows_returns_full_registry(self):
        rows = [{
            "id": 1,
            "name": "Alistair",
            "alias": None,
            "faction": None,
            "status": "alive",
            "last_known_location": "Coast near Catur",
            "first_seen_session": 20,
            "description": "Boat contact.",
            "is_named": True,
            "notes": "",
        }]
        with patch("web_review.db.fetch_all", return_value=rows) as fetch:
            self.assertEqual(canon.npc_rows(), rows)
        self.assertIn("LEFT JOIN entity_status", fetch.call_args.args[0])
        self.assertIn("LEFT JOIN session fs", fetch.call_args.args[0])

    def test_npc_crud_services_run_expected_statements(self):
        values = {
            "name": "New NPC",
            "alias": "",
            "faction_id": None,
            "entity_status_id": 1,
            "last_known_location_id": 2,
            "first_seen_session": 21,
            "description": "A newly met person.",
            "is_named": True,
            "notes": "",
        }
        with patch("web_review.db.execute") as execute:
            canon.create_npc(values)
            canon.update_npc(12, values)
            canon.delete_npc(12)

        self.assertIn("INSERT INTO npc", execute.call_args_list[0].args[0])
        self.assertIn("SELECT id FROM session WHERE session_number = :first_seen_session", execute.call_args_list[0].args[0])
        self.assertIn("UPDATE npc", execute.call_args_list[1].args[0])
        self.assertIn("DELETE FROM npc", execute.call_args_list[2].args[0])

    def test_artifact_rows_returns_full_ledger(self):
        rows = [{
            "id": 1,
            "name": "The Black Blade",
            "artifact_type": "weapon",
            "discovered_session": 20,
            "description": "Matte black blade.",
            "lore_significance": "Feels like a decision already made.",
            "is_sentient": False,
            "is_cursed": False,
            "is_infernal": False,
            "current_holder": "Faban Colon",
            "notes": "Given by Balrog dwarves, Session 20",
        }]
        with patch("web_review.db.fetch_all", return_value=rows) as fetch:
            self.assertEqual(canon.artifact_rows(), rows)
        self.assertIn("LEFT JOIN artifact_type", fetch.call_args.args[0])
        self.assertIn("artifact_custody", fetch.call_args.args[0])

    def test_artifact_crud_services_run_expected_statements(self):
        values = {
            "name": "New Relic",
            "artifact_type_id": 1,
            "discovered_session": 21,
            "description": "A newly found relic.",
            "lore_significance": "It hums quietly.",
            "is_sentient": False,
            "is_cursed": False,
            "is_infernal": True,
            "notes": "",
        }
        with patch("web_review.db.execute") as execute:
            canon.create_artifact(values)
            canon.update_artifact(12, values)
            canon.delete_artifact(12)

        self.assertIn("INSERT INTO artifact", execute.call_args_list[0].args[0])
        self.assertIn("SELECT id FROM session WHERE session_number = :discovered_session", execute.call_args_list[0].args[0])
        self.assertIn("UPDATE artifact", execute.call_args_list[1].args[0])
        self.assertIn("DELETE FROM artifact", execute.call_args_list[2].args[0])

    def test_lore_item_rows_returns_full_registry(self):
        rows = [{
            "id": 1,
            "title": "Catur Distrusts Above-Folk",
            "category": "culture",
            "description": "Catur distrusts surface dwellers because poachers and pirates intrude on its waters.",
            "source_npc": "Queen of Catur",
            "discovered_session": 21,
            "is_confirmed": True,
            "notes": "Confirmed during the Catur audience.",
        }]
        with patch("web_review.db.fetch_all", return_value=rows) as fetch:
            self.assertEqual(canon.lore_item_rows(), rows)
        self.assertIn("FROM lore_item", fetch.call_args.args[0])
        self.assertIn("LEFT JOIN npc", fetch.call_args.args[0])
        self.assertIn("LEFT JOIN session ds", fetch.call_args.args[0])

    def test_lore_item_crud_services_run_expected_statements(self):
        values = {
            "title": "New Lore",
            "category": "magic",
            "description": "A newly confirmed rule of magic.",
            "source_npc_id": 2,
            "discovered_session": 21,
            "is_confirmed": True,
            "notes": "",
        }
        with patch("web_review.db.execute") as execute:
            canon.create_lore_item(values)
            canon.update_lore_item(12, values)
            canon.delete_lore_item(12)

        self.assertIn("INSERT INTO lore_item", execute.call_args_list[0].args[0])
        self.assertIn("SELECT id FROM session WHERE session_number = :discovered_session", execute.call_args_list[0].args[0])
        self.assertIn("UPDATE lore_item", execute.call_args_list[1].args[0])
        self.assertIn("DELETE FROM lore_item", execute.call_args_list[2].args[0])

    def test_combat_encounter_rows_groups_enemies_and_unknown_quantities(self):
        db_rows = [
            {
                "id": 1,
                "session_number": 19,
                "session_title": "Of Teeth, Memory, and What Remains",
                "title": "Orsydon summoned in Balrog",
                "subtype": "dragon_summoning",
                "location": "Balrog",
                "participants": "Party, Orsydon, cultists",
                "outcome": "dragon_defeated",
                "confidence": "high",
                "notes": "Cultists summon Orsydon.",
                "enemy_name": "Cultist",
                "enemy_type": "cultist",
                "quantity": None,
                "quantity_killed": None,
                "enemy_outcome": "defeated",
                "enemy_confidence": "medium",
                "enemy_notes": "Count unknown.",
            },
            {
                "id": 1,
                "session_number": 19,
                "session_title": "Of Teeth, Memory, and What Remains",
                "title": "Orsydon summoned in Balrog",
                "subtype": "dragon_summoning",
                "location": "Balrog",
                "participants": "Party, Orsydon, cultists",
                "outcome": "dragon_defeated",
                "confidence": "high",
                "notes": "Cultists summon Orsydon.",
                "enemy_name": "Orsydon",
                "enemy_type": "dragon",
                "quantity": 1,
                "quantity_killed": 1,
                "enemy_outcome": "defeated",
                "enemy_confidence": "high",
                "enemy_notes": "Dragon defeated.",
            },
        ]
        with patch("web_review.db.fetch_all", return_value=db_rows) as fetch:
            rows = canon.combat_encounter_rows()

        self.assertIn("WHERE c.encounter_type = 'combat'", fetch.call_args.args[0])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["known_enemy_total"], 1)
        self.assertTrue(rows[0]["has_unknown_quantity"])
        self.assertEqual(rows[0]["enemies"][1]["quantity_killed"], 1)
        self.assertEqual([enemy["name"] for enemy in rows[0]["enemies"]], ["Cultist", "Orsydon"])

    def test_combat_encounter_rows_labels_spanning_combat(self):
        db_rows = [{
            "id": 2,
            "session_number": 0,
            "session_title": "The Party forms",
            "title": "Rock-being street attack",
            "subtype": "construct_attack",
            "location": "Bentrios",
            "participants": "Party, regenerating construct",
            "outcome": "continues_into_session01",
            "confidence": "high",
            "notes": "Continues into the next session.",
            "enemy_name": "Regenerating construct",
            "enemy_type": "construct",
            "quantity": 1,
            "quantity_killed": 1,
            "enemy_outcome": "defeated",
            "enemy_confidence": "high",
            "enemy_notes": "",
        }]
        with patch("web_review.db.fetch_all", return_value=db_rows):
            rows = canon.combat_encounter_rows()

        self.assertEqual(rows[0]["session_span"], "Session 00 -> Session 01")

    def test_murder_hobo_count_sums_quantity_killed(self):
        summary = canon.murder_hobo_count([
            {
                "enemies": [
                    {"quantity": 3, "quantity_killed": 1, "outcome": "fled"},
                    {"quantity": 2, "quantity_killed": 2, "outcome": "killed"},
                    {"quantity": 5, "quantity_killed": 0, "outcome": "fled"},
                    {"quantity": None, "quantity_killed": None, "outcome": "killed"},
                    {"quantity": 3, "quantity_killed": None, "outcome": "defeated_or_fled"},
                ],
            }
        ])

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["unknown_rows"], 1)
        self.assertEqual(summary["label"], "3+ unknown")

    def test_songbook_rows_marks_local_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lyrics = root / "knowledge" / "Faban" / "songbook" / "Song" / "lyrics.md"
            audio = lyrics.parent / "song.mp3"
            lyrics.parent.mkdir(parents=True)
            lyrics.write_text("Verse", encoding="utf-8")
            audio.write_bytes(b"mp3")
            db_rows = [{
                "id": 1,
                "song_number": 1,
                "order_number": 1,
                "title": "Test Song",
                "style_id": 1,
                "style": "ballad",
                "category_id": 1,
                "category": "lore",
                "song_type": "Test ballad",
                "short_description": "",
                "long_description": "",
                "summary": "",
                "suno_prompt": "",
                "musical_key": "",
                "meter": "4/4",
                "tempo": "90 BPM",
                "instrumentation": "",
                "lyrics_local_path": "knowledge/Faban/songbook/Song/lyrics.md",
                "mp3_local_path": "knowledge/Faban/songbook/Song/song.mp3",
                "mp3_url": "",
                "lyrics_url": "",
                "written_session": None,
                "in_world_context": "",
                "is_performed": True,
            }]

            with patch("web_review.services.canon.REPO_ROOT", root), \
                 patch("web_review.db.fetch_all", return_value=db_rows) as fetch:
                rows = canon.songbook_rows()

        self.assertIn("FROM v_songbook", fetch.call_args.args[0])
        self.assertTrue(rows[0]["has_local_audio"])
        self.assertTrue(rows[0]["has_local_lyrics"])

    def test_songbook_lyrics_reads_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lyrics = root / "knowledge" / "Faban" / "songbook" / "Song" / "lyrics.md"
            lyrics.parent.mkdir(parents=True)
            lyrics.write_text("A line worth singing.", encoding="utf-8")
            db_rows = [{
                "song_number": 2,
                "title": "Test Song",
                "style": "ballad",
                "category": "lore",
                "song_type": "",
                "short_description": "",
                "long_description": "",
                "summary": "",
                "suno_prompt": "",
                "musical_key": "",
                "meter": "",
                "tempo": "",
                "instrumentation": "",
                "lyrics_local_path": "knowledge/Faban/songbook/Song/lyrics.md",
                "mp3_local_path": "",
                "mp3_url": "",
                "lyrics_url": "",
            }]

            with patch("web_review.services.canon.REPO_ROOT", root), \
                 patch("web_review.db.fetch_all", return_value=db_rows):
                self.assertEqual(canon.songbook_lyrics(2), "A line worth singing.")

    def test_songbook_foreword_reads_front_matter_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            foreword = root / "knowledge" / "Faban" / "songbook" / "foreward.md"
            foreword.parent.mkdir(parents=True)
            foreword.write_text("Songs remember what steel forgets.", encoding="utf-8")
            db_rows = [{
                "title": "The Revealed Songbook",
                "foreword_path": "knowledge/Faban/songbook/foreward.md",
                "foreword_text": "",
                "notes": "front matter",
            }]

            with patch("web_review.services.canon.REPO_ROOT", root), \
                 patch("web_review.db.fetch_all", return_value=db_rows) as fetch:
                result = canon.songbook_foreword()

        self.assertIn("songbook_front_matter", fetch.call_args.args[0])
        self.assertEqual(result["title"], "The Revealed Songbook")
        self.assertEqual(result["text"], "Songs remember what steel forgets.")

    def test_songbook_source_sql_updates_urls_by_song_number(self):
        class Asset:
            number = 5
            lyrics_url = "https://docs.example/song"
            mp3_url = "https://drive.example/song.mp3"

        sql = songbook_source_sql(Asset())

        self.assertIn("WHERE song_number = 5", sql)
        self.assertIn("lyrics_url = 'https://docs.example/song'", sql)
        self.assertIn("mp3_url = 'https://drive.example/song.mp3'", sql)

    def test_event_types_returns_ordered_names_from_db_rows(self):
        with patch("web_review.db.fetch_all", return_value=[{"type_name": "combat"}, {"type_name": "social"}]):
            self.assertEqual(canon.event_types(), ["combat", "social"])

    def test_lookup_rows_reads_configured_lookup_table(self):
        with patch("web_review.db.fetch_all", return_value=[{"id": 1, "value": "weapon", "description": None}]) as fetch:
            rows = canon.lookup_rows("artifact-types")

        self.assertEqual(rows[0]["value"], "weapon")
        self.assertIn("FROM artifact_type", fetch.call_args.args[0])

    def test_lookup_rows_include_factions_table(self):
        with patch("web_review.db.fetch_all", return_value=[{"id": 1, "value": "Celestial Isles", "description": "Dragonkin society."}]) as fetch:
            rows = canon.lookup_rows("factions")

        self.assertEqual(rows[0]["value"], "Celestial Isles")
        self.assertIn("FROM faction", fetch.call_args.args[0])
        self.assertIn("name AS value", fetch.call_args.args[0])
        self.assertIn("description AS description", fetch.call_args.args[0])

    def test_custom_lookup_rows_ensures_table_and_seed_values(self):
        with patch("web_review.db.execute") as execute, \
             patch("web_review.db.fetch_all", return_value=[{"id": 1, "value": "defeated", "description": "Done."}]) as fetch:
            rows = canon.lookup_rows("combat-outcomes")

        self.assertEqual(rows[0]["value"], "defeated")
        self.assertIn("CREATE TABLE IF NOT EXISTS combat_outcome", execute.call_args_list[0].args[0])
        self.assertIn("FROM combat_outcome", fetch.call_args.args[0])

    def test_lookup_crud_services_run_expected_statements(self):
        with patch("web_review.db.execute") as execute, \
             patch("web_review.services.canon.persist_lookup_overrides") as persist:
            canon.create_lookup_value("location-types", "ruin")
            canon.update_lookup_value("location-types", 3, "ancient_ruin")
            canon.delete_lookup_value("location-types", 3)

        self.assertIn("INSERT INTO location_type", execute.call_args_list[0].args[0])
        self.assertIn("UPDATE location_type", execute.call_args_list[1].args[0])
        self.assertIn("DELETE FROM location_type", execute.call_args_list[2].args[0])
        self.assertEqual(persist.call_count, 3)

    def test_lookup_override_sql_syncs_campaign_lookup_values(self):
        snapshot = {
            "lookups": {
                "location-types": {
                    "values": [{"value": "settlement"}, {"value": "tavern"}],
                },
                "combat-outcomes": {
                    "values": [{"value": "banished", "description": "Sent away."}],
                },
            },
        }

        sql = canon.lookup_override_sql(snapshot)

        self.assertIn("DELETE FROM location_type WHERE type_name NOT IN ('settlement', 'tavern');", sql)
        self.assertIn("INSERT INTO location_type (type_name) VALUES ('settlement')", sql)
        self.assertIn("DELETE FROM combat_outcome WHERE outcome_code NOT IN ('banished');", sql)
        self.assertIn("ON CONFLICT (outcome_code) DO UPDATE SET description = EXCLUDED.description", sql)


class LocationRouteTest(unittest.TestCase):
    def location_rows(self):
        return [{
            "id": 1,
            "name": "Bentrios",
            "location_type": "city",
            "parent_location": None,
            "description": "Starting city.",
            "is_underwater": False,
            "is_feywild": False,
            "first_visited_session": 0,
            "notes": "",
        }]

    def test_locations_page_renders_sidebar_and_ledger(self):
        with patch("web_review.services.canon.location_rows", return_value=self.location_rows()), \
             patch("web_review.services.canon.location_types", return_value=[{"id": 1, "type_name": "city"}]):
            client = TestClient(app)
            response = client.get("/locations")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Locations", response.text)
        self.assertIn("Bentrios", response.text)
        self.assertIn("Add New", response.text)
        self.assertNotIn("Add Location</h2>", response.text)
        self.assertIn('href="/locations"', response.text)
        self.assertIn("/static/locations-icon.png", response.text)

    def test_locations_add_modal_renders_form(self):
        with patch("web_review.services.canon.location_rows", return_value=self.location_rows()), \
             patch("web_review.services.canon.location_types", return_value=[{"id": 1, "type_name": "city"}]):
            client = TestClient(app)
            response = client.get("/locations?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Location", response.text)
        self.assertIn("/static/location-edit-icon.png", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn('action="/locations"', response.text)

    def test_archive_mode_hides_location_edit_controls(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.canon.location_rows", return_value=self.location_rows()), \
             patch("web_review.services.canon.location_types", return_value=[{"id": 1, "type_name": "city"}]):
            client = TestClient(app)
            response = client.get("/locations?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Published Archive", response.text)
        self.assertNotIn("Add New", response.text)
        self.assertNotIn("Edit</a>", response.text)
        self.assertNotIn("Delete</button>", response.text)
        self.assertNotIn("workflow-detail-modal", response.text)

    def test_create_location_route_writes_form_values(self):
        with patch("web_review.services.canon.create_location") as create:
            client = TestClient(app)
            response = client.post("/locations", data={
                "name": "Road to Balrog",
                "location_type_id": "9",
                "parent_location_id": "",
                "description": "A mountain road.",
                "is_underwater": "",
                "is_feywild": "on",
                "first_visited_session": "16",
                "notes": "Cold and dangerous.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("created=1", response.headers["location"])
        create.assert_called_once()
        values = create.call_args.args[0]
        self.assertEqual(values["name"], "Road to Balrog")
        self.assertEqual(values["location_type_id"], 9)
        self.assertTrue(values["is_feywild"])
        self.assertEqual(values["first_visited_session"], 16)

    def test_edit_location_page_loads_location(self):
        detail = {
            "id": 1,
            "name": "Bentrios",
            "location_type_id": 1,
            "parent_location_id": None,
            "description": "Starting city.",
            "is_underwater": False,
            "is_feywild": False,
            "first_visited_session": 0,
            "notes": "",
        }
        with patch("web_review.services.canon.location_rows", return_value=self.location_rows()), \
             patch("web_review.services.canon.location_types", return_value=[{"id": 1, "type_name": "city"}]), \
             patch("web_review.services.canon.location_detail", return_value=detail):
            client = TestClient(app)
            response = client.get("/locations/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Edit Location", response.text)
        self.assertIn("/static/location-edit-icon.png", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn("Starting city.", response.text)

    def test_update_location_route_writes_form_values(self):
        with patch("web_review.services.canon.update_location") as update:
            client = TestClient(app)
            response = client.post("/locations/3", data={
                "name": "Catur",
                "location_type_id": "5",
                "parent_location_id": "",
                "description": "Sunken city.",
                "is_underwater": "on",
                "first_visited_session": "20",
                "notes": "",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("updated=1", response.headers["location"])
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], 3)
        self.assertTrue(update.call_args.args[1]["is_underwater"])

    def test_delete_location_route_runs_delete(self):
        with patch("web_review.services.canon.delete_location") as delete:
            client = TestClient(app)
            response = client.post("/locations/4/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("deleted=1", response.headers["location"])
        delete.assert_called_once_with(4)

    def test_archive_mode_blocks_location_mutation(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.canon.create_location") as create:
            client = TestClient(app)
            response = client.post("/locations", data={"name": "Hidden Gate"}, follow_redirects=False)

        self.assertEqual(response.status_code, 403)
        self.assertIn("archive mode", response.text)
        create.assert_not_called()


class LocationExtractionReviewRouteTest(unittest.TestCase):
    def extraction(self):
        return {
            "path": Path("/tmp/session21_locations.json"),
            "session_number": 21,
            "known_location_mentions": [{
                "location_id": 5,
                "canonical_name": "Catur",
                "mentioned_as": ["Catur"],
                "new_information": "Confirmed as an underwater city.",
                "location_type": "city",
                "parent_location": "",
                "is_underwater": True,
                "is_feywild": False,
                "confidence": "high",
                "evidence": "Catur lies beneath the ocean.",
            }],
            "new_location_candidates": [{
                "proposed_name": "Catur's Well Chamber",
                "location_type": "chamber",
                "description": "Underwater well chamber.",
                "first_visited_session": 21,
                "parent_location": "Catur",
                "is_underwater": True,
                "is_feywild": False,
                "confidence": "high",
                "evidence": "The party entered the well chamber.",
            }],
            "rejected_candidates": [{"text": "surface", "reason": "Generic direction."}],
            "uncertainties": [{"candidate": "Pearl of Atlantia", "issue": "Artifact, not location."}],
        }

    def test_location_extraction_review_page_renders_decisions(self):
        with patch.object(location_extraction_review, "available_sessions", return_value=[20, 21]), \
             patch.object(location_extraction_review, "load_extraction", return_value=self.extraction()), \
             patch.object(location_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_locations_reviewed.json")):
            client = TestClient(app)
            response = client.get("/locations/extractions?session=21")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Location Extraction Review", response.text)
        self.assertIn("Catur", response.text)
        self.assertIn("Catur&#39;s Well Chamber", response.text)
        self.assertIn('name="known_decision_0"', response.text)
        self.assertIn('name="new_decision_0"', response.text)
        self.assertIn("Generic direction.", response.text)
        self.assertIn("Artifact, not location.", response.text)

    def test_location_extraction_review_defaults_to_latest_available_session(self):
        with patch.object(location_extraction_review, "available_sessions", return_value=[20, 21]), \
             patch.object(location_extraction_review, "load_extraction", return_value=self.extraction()) as load, \
             patch.object(location_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_locations_reviewed.json")):
            client = TestClient(app)
            response = client.get("/locations/extractions")

        self.assertEqual(response.status_code, 200)
        load.assert_called_once_with(21)
        self.assertIn('value="21"', response.text)

    def test_apply_location_extraction_review_posts_decisions(self):
        result = {"applied": ["Updated Catur", "Created Catur's Well Chamber"], "skipped": [], "reviewed_path": Path("/tmp/reviewed.json")}
        with patch.object(location_extraction_review, "apply_review", return_value=result) as apply_review, \
             patch("web_review.services.workflow.sync_session_workflow") as sync:
            client = TestClient(app)
            response = client.post("/locations/extractions/apply", data={
                "session_number": "21",
                "known_decision_0": "append_note",
                "new_decision_0": "create",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/locations/extractions?session=21", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        apply_review.assert_called_once()
        self.assertEqual(apply_review.call_args.args[0], 21)
        self.assertEqual(apply_review.call_args.args[1]["new_decision_0"], "create")
        sync.assert_called_once_with(21)

    def test_apply_location_extraction_review_reports_failure_detail(self):
        with patch.object(location_extraction_review, "apply_review", side_effect=location_extraction_review.LocationExtractionReviewError("bad location")):
            client = TestClient(app)
            response = client.post("/locations/extractions/apply", data={
                "session_number": "21",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("apply_failed=1", response.headers["location"])
        token = response.headers["location"].split("command_result=", 1)[1]
        self.assertEqual(COMMAND_RESULTS[token]["stderr"], "bad location")

    def test_post_extraction_review_initializes_event_review_when_all_reviews_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "session02_review.yaml"
            with patch.object(reviews, "event_review_ready", return_value=True), \
                 patch.object(reviews, "review_path", return_value=review_path), \
                 patch("web_review.services.commands.refresh_event_drafts", return_value=commands.CommandResult(0, "Refreshed events", "")) as refresh, \
                 patch("web_review.services.commands.init_review", return_value=commands.CommandResult(0, "Wrote review", "")) as init, \
                 patch("web_review.services.workflow.sync_session_workflow") as sync:
                messages = sync_after_extraction_review(2)

        refresh.assert_called_once_with(2)
        init.assert_called_once_with(2)
        self.assertEqual(sync.call_count, 3)
        self.assertIn("Refreshed event drafts.", messages)
        self.assertIn("Initialized final summary review.", messages)

    def test_post_extraction_review_does_not_initialize_when_event_refresh_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "session02_review.yaml"
            with patch.object(reviews, "event_review_ready", return_value=True), \
                 patch.object(reviews, "review_path", return_value=review_path), \
                 patch("web_review.services.commands.refresh_event_drafts", return_value=commands.CommandResult(1, "", "extract failed")) as refresh, \
                 patch("web_review.services.commands.init_review") as init, \
                 patch("web_review.services.workflow.sync_session_workflow") as sync:
                messages = sync_after_extraction_review(2)

        refresh.assert_called_once_with(2)
        init.assert_not_called()
        sync.assert_called_once_with(2)
        self.assertIn("Event draft refresh failed.", messages)
        self.assertIn("extract failed", messages)

    def test_archive_mode_blocks_location_extraction_review_page(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/locations/extractions")

        self.assertEqual(response.status_code, 404)


class NPCRouteTest(unittest.TestCase):
    def npc_rows(self):
        return [{
            "id": 1,
            "name": "Alistair",
            "alias": "",
            "faction": None,
            "status": "alive",
            "last_known_location": "Coast near Catur",
            "first_seen_session": 20,
            "description": "Coastal boat contact.",
            "is_named": True,
            "notes": "",
        }]

    def support_rows(self):
        return {
            "statuses": [{"id": 1, "status_code": "alive"}],
            "factions": [{"id": 2, "name": "Dwarves of Balrog"}],
            "locations": [{"id": 3, "name": "Coast near Catur"}],
        }

    def test_npcs_page_renders_sidebar_and_ledger(self):
        support = self.support_rows()
        with patch("web_review.services.canon.npc_rows", return_value=self.npc_rows()), \
             patch("web_review.services.canon.entity_statuses", return_value=support["statuses"]), \
             patch("web_review.services.canon.factions", return_value=support["factions"]), \
             patch("web_review.services.canon.location_rows", return_value=support["locations"]):
            client = TestClient(app)
            response = client.get("/npcs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("NPC Registry", response.text)
        self.assertIn("Alistair", response.text)
        self.assertIn("Coast near Catur", response.text)
        self.assertIn('href="/npcs"', response.text)
        self.assertIn("/static/npc-registry-icon.png", response.text)
        self.assertIn("Add New", response.text)
        self.assertNotIn("Add NPC</h2>", response.text)

    def test_npcs_add_modal_renders_form(self):
        support = self.support_rows()
        with patch("web_review.services.canon.npc_rows", return_value=self.npc_rows()), \
             patch("web_review.services.canon.entity_statuses", return_value=support["statuses"]), \
             patch("web_review.services.canon.factions", return_value=support["factions"]), \
             patch("web_review.services.canon.location_rows", return_value=support["locations"]):
            client = TestClient(app)
            response = client.get("/npcs?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add NPC", response.text)
        self.assertIn("/static/npc-edit-icon.png", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn('action="/npcs"', response.text)

    def test_archive_mode_hides_npc_edit_controls(self):
        support = self.support_rows()
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.canon.npc_rows", return_value=self.npc_rows()), \
             patch("web_review.services.canon.entity_statuses", return_value=support["statuses"]), \
             patch("web_review.services.canon.factions", return_value=support["factions"]), \
             patch("web_review.services.canon.location_rows", return_value=support["locations"]):
            client = TestClient(app)
            response = client.get("/npcs?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add New", response.text)
        self.assertNotIn("Edit</a>", response.text)
        self.assertNotIn("Delete</button>", response.text)
        self.assertNotIn("workflow-detail-modal", response.text)

    def test_create_npc_route_writes_form_values(self):
        with patch("web_review.services.canon.create_npc") as create:
            client = TestClient(app)
            response = client.post("/npcs", data={
                "name": "Captain Myra",
                "alias": "The Tide Hand",
                "faction_id": "",
                "entity_status_id": "1",
                "last_known_location_id": "3",
                "first_seen_session": "21",
                "description": "A sea captain.",
                "is_named": "on",
                "notes": "Potential ally.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("created=1", response.headers["location"])
        create.assert_called_once()
        values = create.call_args.args[0]
        self.assertEqual(values["name"], "Captain Myra")
        self.assertEqual(values["entity_status_id"], 1)
        self.assertEqual(values["last_known_location_id"], 3)
        self.assertEqual(values["first_seen_session"], 21)
        self.assertTrue(values["is_named"])

    def test_edit_npc_page_loads_npc(self):
        support = self.support_rows()
        detail = {
            "id": 1,
            "name": "Alistair",
            "alias": "",
            "faction_id": None,
            "entity_status_id": 1,
            "last_known_location_id": 3,
            "first_seen_session": 20,
            "description": "Coastal boat contact.",
            "is_named": True,
            "notes": "",
        }
        with patch("web_review.services.canon.npc_rows", return_value=self.npc_rows()), \
             patch("web_review.services.canon.entity_statuses", return_value=support["statuses"]), \
             patch("web_review.services.canon.factions", return_value=support["factions"]), \
             patch("web_review.services.canon.location_rows", return_value=support["locations"]), \
             patch("web_review.services.canon.npc_detail", return_value=detail):
            client = TestClient(app)
            response = client.get("/npcs/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Edit NPC", response.text)
        self.assertIn("/static/npc-edit-icon.png", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn("Coastal boat contact.", response.text)

    def test_update_npc_route_writes_form_values(self):
        with patch("web_review.services.canon.update_npc") as update:
            client = TestClient(app)
            response = client.post("/npcs/3", data={
                "name": "Alistair",
                "entity_status_id": "1",
                "last_known_location_id": "3",
                "first_seen_session": "20",
                "description": "Boat contact.",
                "is_named": "on",
                "notes": "",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("updated=1", response.headers["location"])
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], 3)
        self.assertEqual(update.call_args.args[1]["first_seen_session"], 20)

    def test_delete_npc_route_runs_delete(self):
        with patch("web_review.services.canon.delete_npc") as delete:
            client = TestClient(app)
            response = client.post("/npcs/4/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("deleted=1", response.headers["location"])
        delete.assert_called_once_with(4)


class NPCExtractionReviewRouteTest(unittest.TestCase):
    def extraction(self):
        return {
            "path": Path("/tmp/session21_npcs.json"),
            "session_number": 21,
            "known_npc_mentions": [{
                "npc_id": 12,
                "canonical_name": "Alistair",
                "mentioned_as": ["Allister"],
                "new_information": "Warned that Catur dislikes outsiders.",
                "location": "Coast near Catur",
                "confidence": "high",
                "evidence": "Allister warned Faban.",
            }],
            "new_npc_candidates": [{
                "proposed_name": "Uthgar",
                "npc_kind": "named_npc",
                "role": "Catur smith",
                "description": "Underwater smith contact.",
                "first_seen_session": 21,
                "first_seen_location": "Catur",
                "status": "alive",
                "confidence": "high",
                "evidence": "They learned the smith was Uthgar.",
            }],
            "rejected_candidates": [{"text": "Mikani", "reason": "Player character."}],
            "uncertainties": [{"candidate": "Niebain", "issue": "Spelling uncertain."}],
        }

    def test_npc_extraction_review_page_renders_decisions(self):
        with patch.object(npc_extraction_review, "available_sessions", return_value=[19, 20, 21]), \
             patch.object(npc_extraction_review, "load_extraction", return_value=self.extraction()), \
             patch.object(npc_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_npcs_reviewed.json")):
            client = TestClient(app)
            response = client.get("/npcs/extractions?session=21")

        self.assertEqual(response.status_code, 200)
        self.assertIn("NPC Extraction Review", response.text)
        self.assertIn("Alistair", response.text)
        self.assertIn("Uthgar", response.text)
        self.assertIn('name="known_decision_0"', response.text)
        self.assertIn('name="new_decision_0"', response.text)
        self.assertIn("Player character.", response.text)
        self.assertIn("Spelling uncertain.", response.text)

    def test_npc_extraction_review_defaults_to_latest_available_session(self):
        with patch.object(npc_extraction_review, "available_sessions", return_value=[19, 20, 21]), \
             patch.object(npc_extraction_review, "load_extraction", return_value=self.extraction()) as load, \
             patch.object(npc_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_npcs_reviewed.json")):
            client = TestClient(app)
            response = client.get("/npcs/extractions")

        self.assertEqual(response.status_code, 200)
        load.assert_called_once_with(21)
        self.assertIn('value="21"', response.text)

    def test_apply_npc_extraction_review_posts_decisions(self):
        result = {"applied": ["Updated Alistair", "Created Uthgar"], "skipped": [], "reviewed_path": Path("/tmp/reviewed.json")}
        with patch.object(npc_extraction_review, "apply_review", return_value=result) as apply_review:
            client = TestClient(app)
            response = client.post("/npcs/extractions/apply", data={
                "session_number": "21",
                "known_decision_0": "append_note",
                "new_decision_0": "create",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/npcs/extractions?session=21", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        apply_review.assert_called_once()
        self.assertEqual(apply_review.call_args.args[0], 21)
        self.assertEqual(apply_review.call_args.args[1]["new_decision_0"], "create")

    def test_archive_mode_blocks_npc_extraction_review_page(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/npcs/extractions")

        self.assertEqual(response.status_code, 404)


class ArtifactRouteTest(unittest.TestCase):
    def artifact_rows(self):
        return [{
            "id": 1,
            "name": "The Black Blade",
            "artifact_type": "weapon",
            "discovered_session": 20,
            "description": "Matte black blade.",
            "lore_significance": "Feels like a decision already made.",
            "is_sentient": False,
            "is_cursed": False,
            "is_infernal": False,
            "current_holder": "Faban Colon",
            "notes": "Given by Balrog dwarves, Session 20",
        }]

    def artifact_types(self):
        return [{"id": 1, "type_name": "weapon"}]

    def test_artifacts_page_renders_sidebar_and_ledger(self):
        with patch("web_review.services.canon.artifact_rows", return_value=self.artifact_rows()), \
             patch("web_review.services.canon.artifact_types", return_value=self.artifact_types()):
            client = TestClient(app)
            response = client.get("/artifacts")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Artifacts", response.text)
        self.assertIn("The Black Blade", response.text)
        self.assertIn('title="Given by Balrog dwarves, Session 20"', response.text)
        self.assertIn("Faban Colon", response.text)
        self.assertIn('href="/artifacts"', response.text)
        self.assertIn("/static/artifacts-icon.png", response.text)
        self.assertIn("Add New", response.text)
        self.assertNotIn("Add Artifact</h2>", response.text)

    def test_artifacts_add_modal_renders_form(self):
        with patch("web_review.services.canon.artifact_rows", return_value=self.artifact_rows()), \
             patch("web_review.services.canon.artifact_types", return_value=self.artifact_types()):
            client = TestClient(app)
            response = client.get("/artifacts?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Artifact", response.text)
        self.assertIn("/static/artifact-edit-icon.png", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn('action="/artifacts"', response.text)

    def test_archive_mode_hides_artifact_edit_controls(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.canon.artifact_rows", return_value=self.artifact_rows()), \
             patch("web_review.services.canon.artifact_types", return_value=self.artifact_types()):
            client = TestClient(app)
            response = client.get("/artifacts?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add New", response.text)
        self.assertNotIn("Edit</a>", response.text)
        self.assertNotIn("Delete</button>", response.text)
        self.assertNotIn("workflow-detail-modal", response.text)

    def test_create_artifact_route_writes_form_values(self):
        with patch("web_review.services.canon.create_artifact") as create:
            client = TestClient(app)
            response = client.post("/artifacts", data={
                "name": "Moon Compass",
                "artifact_type_id": "1",
                "discovered_session": "21",
                "description": "A compass that ignores north.",
                "lore_significance": "Points toward promises.",
                "is_sentient": "",
                "is_cursed": "",
                "is_infernal": "on",
                "notes": "Suspicious.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("created=1", response.headers["location"])
        create.assert_called_once()
        values = create.call_args.args[0]
        self.assertEqual(values["name"], "Moon Compass")
        self.assertEqual(values["artifact_type_id"], 1)
        self.assertEqual(values["discovered_session"], 21)
        self.assertTrue(values["is_infernal"])

    def test_edit_artifact_page_loads_artifact(self):
        detail = {
            "id": 1,
            "name": "The Black Blade",
            "artifact_type_id": 1,
            "discovered_session": 20,
            "description": "Matte black blade.",
            "lore_significance": "Feels like a decision already made.",
            "is_sentient": False,
            "is_cursed": False,
            "is_infernal": False,
            "notes": "",
        }
        with patch("web_review.services.canon.artifact_rows", return_value=self.artifact_rows()), \
             patch("web_review.services.canon.artifact_types", return_value=self.artifact_types()), \
             patch("web_review.services.canon.artifact_detail", return_value=detail):
            client = TestClient(app)
            response = client.get("/artifacts/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Edit Artifact", response.text)
        self.assertIn("/static/artifact-edit-icon.png", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn("Matte black blade.", response.text)

    def test_update_artifact_route_writes_form_values(self):
        with patch("web_review.services.canon.update_artifact") as update:
            client = TestClient(app)
            response = client.post("/artifacts/3", data={
                "name": "The Black Blade",
                "artifact_type_id": "1",
                "discovered_session": "20",
                "description": "Matte black blade.",
                "lore_significance": "Still unnerving.",
                "is_sentient": "",
                "is_cursed": "on",
                "is_infernal": "",
                "notes": "",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("updated=1", response.headers["location"])
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], 3)
        self.assertTrue(update.call_args.args[1]["is_cursed"])

    def test_delete_artifact_route_runs_delete(self):
        with patch("web_review.services.canon.delete_artifact") as delete:
            client = TestClient(app)
            response = client.post("/artifacts/4/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("deleted=1", response.headers["location"])
        delete.assert_called_once_with(4)


class ArtifactExtractionReviewRouteTest(unittest.TestCase):
    def extraction(self):
        return {
            "path": Path("/tmp/session21_artifacts.json"),
            "session_number": 21,
            "known_artifact_mentions": [{
                "artifact_id": 5,
                "canonical_name": "Acheron Blade",
                "mentioned_as": ["Acheron Blade"],
                "new_information": "Clarified as a +1 weapon.",
                "artifact_type": "weapon",
                "current_holder": "Faban",
                "properties": ["+1 weapon"],
                "is_sentient": False,
                "is_cursed": False,
                "is_infernal": True,
                "confidence": "high",
                "evidence": "Faban clarified the Acheron Blade.",
            }],
            "new_artifact_candidates": [{
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
                "confidence": "high",
                "evidence": "Mikani has a cap.",
            }],
            "rejected_candidates": [{"text": "socks", "reason": "Joke item."}],
            "uncertainties": [{"candidate": "Pearl of Atlantia", "issue": "Spelling uncertain."}],
        }

    def test_artifact_extraction_review_page_renders_decisions(self):
        with patch.object(artifact_extraction_review, "available_sessions", return_value=[20, 21]), \
             patch.object(artifact_extraction_review, "load_extraction", return_value=self.extraction()), \
             patch.object(artifact_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_artifacts_reviewed.json")):
            client = TestClient(app)
            response = client.get("/artifacts/extractions?session=21")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Artifact Extraction Review", response.text)
        self.assertIn("Acheron Blade", response.text)
        self.assertIn("Cap of Water Breathing", response.text)
        self.assertIn('name="known_decision_0"', response.text)
        self.assertIn('name="new_decision_0"', response.text)
        self.assertIn("Joke item.", response.text)
        self.assertIn("Spelling uncertain.", response.text)

    def test_artifact_extraction_review_defaults_to_latest_available_session(self):
        with patch.object(artifact_extraction_review, "available_sessions", return_value=[20, 21]), \
             patch.object(artifact_extraction_review, "load_extraction", return_value=self.extraction()) as load, \
             patch.object(artifact_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_artifacts_reviewed.json")):
            client = TestClient(app)
            response = client.get("/artifacts/extractions")

        self.assertEqual(response.status_code, 200)
        load.assert_called_once_with(21)
        self.assertIn('value="21"', response.text)

    def test_apply_artifact_extraction_review_posts_decisions(self):
        result = {"applied": ["Updated Acheron Blade", "Created Cap of Water Breathing"], "skipped": [], "reviewed_path": Path("/tmp/reviewed.json")}
        with patch.object(artifact_extraction_review, "apply_review", return_value=result) as apply_review, \
             patch("web_review.services.workflow.sync_session_workflow") as sync:
            client = TestClient(app)
            response = client.post("/artifacts/extractions/apply", data={
                "session_number": "21",
                "known_decision_0": "append_note",
                "new_decision_0": "create",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/artifacts/extractions?session=21", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        apply_review.assert_called_once()
        self.assertEqual(apply_review.call_args.args[0], 21)
        self.assertEqual(apply_review.call_args.args[1]["new_decision_0"], "create")
        sync.assert_called_once_with(21)

    def test_archive_mode_blocks_artifact_extraction_review_page(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/artifacts/extractions")

        self.assertEqual(response.status_code, 404)


class LoreItemRouteTest(unittest.TestCase):
    def lore_rows(self):
        return [{
            "id": 1,
            "title": "Catur Distrusts Above-Folk",
            "category": "culture",
            "description": "Catur distrusts surface dwellers because poachers and pirates intrude on its waters.",
            "source_npc": "Queen of Catur",
            "discovered_session": 21,
            "is_confirmed": True,
            "notes": "Confirmed during the Catur audience.",
        }]

    def categories(self):
        return ["culture", "well_knowledge"]

    def npcs(self):
        return [{"id": 1, "name": "Queen of Catur"}]

    def test_lore_items_page_renders_sidebar_and_ledger(self):
        with patch("web_review.services.canon.lore_item_rows", return_value=self.lore_rows()), \
             patch("web_review.services.canon.lore_categories", return_value=self.categories()), \
             patch("web_review.services.canon.npc_rows", return_value=self.npcs()):
            client = TestClient(app)
            response = client.get("/lore-items")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Lore Items", response.text)
        self.assertIn("Catur Distrusts Above-Folk", response.text)
        self.assertIn('href="/lore-items"', response.text)
        self.assertIn('aria-label="Edit Catur Distrusts Above-Folk"', response.text)
        self.assertIn('aria-label="Delete Catur Distrusts Above-Folk"', response.text)
        self.assertIn("Add New", response.text)

    def test_lore_items_add_modal_renders_form(self):
        with patch("web_review.services.canon.lore_item_rows", return_value=self.lore_rows()), \
             patch("web_review.services.canon.lore_categories", return_value=self.categories()), \
             patch("web_review.services.canon.npc_rows", return_value=self.npcs()):
            client = TestClient(app)
            response = client.get("/lore-items?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Lore Item", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn('action="/lore-items"', response.text)

    def test_archive_mode_hides_lore_item_edit_controls(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.canon.lore_item_rows", return_value=self.lore_rows()), \
             patch("web_review.services.canon.lore_categories", return_value=self.categories()), \
             patch("web_review.services.canon.npc_rows", return_value=self.npcs()):
            client = TestClient(app)
            response = client.get("/lore-items?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Published Archive", response.text)
        self.assertNotIn("Add New", response.text)
        self.assertNotIn('aria-label="Edit Catur Distrusts Above-Folk"', response.text)
        self.assertNotIn('aria-label="Delete Catur Distrusts Above-Folk"', response.text)

    def test_create_lore_item_route_writes_form_values(self):
        with patch("web_review.services.canon.create_lore_item") as create:
            client = TestClient(app)
            response = client.post("/lore-items", data={
                "title": "Catur Distrusts Above-Folk",
                "category": "culture",
                "description": "Catur distrusts surface dwellers.",
                "source_npc_id": "1",
                "discovered_session": "21",
                "is_confirmed": "on",
                "notes": "Queen audience.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("created=1", response.headers["location"])
        create.assert_called_once()
        values = create.call_args.args[0]
        self.assertEqual(values["title"], "Catur Distrusts Above-Folk")
        self.assertEqual(values["source_npc_id"], 1)
        self.assertEqual(values["discovered_session"], 21)
        self.assertTrue(values["is_confirmed"])

    def test_edit_lore_item_page_loads_lore_item(self):
        detail = {
            "id": 1,
            "title": "Catur Distrusts Above-Folk",
            "category": "culture",
            "description": "Catur distrusts surface dwellers.",
            "source_npc_id": 1,
            "discovered_session": 21,
            "is_confirmed": True,
            "notes": "",
        }
        with patch("web_review.services.canon.lore_item_rows", return_value=self.lore_rows()), \
             patch("web_review.services.canon.lore_categories", return_value=self.categories()), \
             patch("web_review.services.canon.npc_rows", return_value=self.npcs()), \
             patch("web_review.services.canon.lore_item_detail", return_value=detail):
            client = TestClient(app)
            response = client.get("/lore-items/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Edit Lore Item", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn("Catur distrusts surface dwellers.", response.text)

    def test_update_lore_item_route_writes_form_values(self):
        with patch("web_review.services.canon.update_lore_item") as update:
            client = TestClient(app)
            response = client.post("/lore-items/3", data={
                "title": "Catur Distrusts Above-Folk",
                "category": "culture",
                "description": "Catur distrusts surface dwellers.",
                "source_npc_id": "",
                "discovered_session": "21",
                "is_confirmed": "",
                "notes": "",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("updated=1", response.headers["location"])
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], 3)
        self.assertFalse(update.call_args.args[1]["is_confirmed"])

    def test_delete_lore_item_route_runs_delete(self):
        with patch("web_review.services.canon.delete_lore_item") as delete:
            client = TestClient(app)
            response = client.post("/lore-items/4/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("deleted=1", response.headers["location"])
        delete.assert_called_once_with(4)

    def extraction(self):
        return {
            "path": Path("/tmp/session21_lore_items.json"),
            "known_lore_mentions": [{
                "lore_item_id": 1,
                "canonical_title": "Catur Distrusts Above-Folk",
                "new_information": "The queen restricted the party to a courtyard.",
                "category": "culture",
                "source_npc": "Queen of Catur",
                "is_confirmed": True,
                "confidence": "high",
                "evidence": "The party was granted access to a courtyard area.",
            }],
            "new_lore_candidates": [{
                "proposed_title": "Celestial Isles Are Draconic",
                "category": "culture",
                "description": "The Celestial Isles are home to dragonborn and kobolds.",
                "source_npc": "Mikani",
                "discovered_session": 21,
                "is_confirmed": True,
                "confidence": "high",
                "evidence": "The Isles are largely draconic.",
            }],
            "rejected_candidates": [{"text": "Faban hates boats", "reason": "Character color."}],
            "uncertainties": [{"candidate": "Niebain / Nebain", "issue": "Spelling uncertain."}],
        }

    def test_lore_item_extraction_review_page_renders_decisions(self):
        with patch.object(lore_item_extraction_review, "available_sessions", return_value=[20, 21]), \
             patch.object(lore_item_extraction_review, "load_extraction", return_value=self.extraction()), \
             patch.object(lore_item_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_lore_items_reviewed.json")):
            client = TestClient(app)
            response = client.get("/lore-items/extractions?session=21")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Lore Item Extraction Review", response.text)
        self.assertIn("Catur Distrusts Above-Folk", response.text)
        self.assertIn("Celestial Isles Are Draconic", response.text)
        self.assertIn('name="known_decision_0"', response.text)
        self.assertIn('name="new_decision_0"', response.text)

    def test_lore_item_extraction_review_defaults_to_latest_available_session(self):
        with patch.object(lore_item_extraction_review, "available_sessions", return_value=[20, 21]), \
             patch.object(lore_item_extraction_review, "load_extraction", return_value=self.extraction()) as load, \
             patch.object(lore_item_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_lore_items_reviewed.json")):
            client = TestClient(app)
            response = client.get("/lore-items/extractions")

        self.assertEqual(response.status_code, 200)
        load.assert_called_once_with(21)

    def test_apply_lore_item_extraction_review_posts_decisions(self):
        result = {"applied": ["Created Celestial Isles Are Draconic"], "skipped": ["Ignored Catur Distrusts Above-Folk"], "reviewed_path": Path("/tmp/reviewed.json")}
        with patch.object(lore_item_extraction_review, "apply_review", return_value=result) as apply_review, \
             patch("web_review.services.workflow.sync_session_workflow") as sync:
            client = TestClient(app)
            response = client.post("/lore-items/extractions/apply", data={
                "session_number": "21",
                "known_decision_0": "ignore",
                "new_decision_0": "create",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/lore-items/extractions?session=21", response.headers["location"])
        apply_review.assert_called_once()
        self.assertEqual(apply_review.call_args.args[0], 21)
        self.assertEqual(apply_review.call_args.args[1]["new_decision_0"], "create")
        sync.assert_called_once_with(21)

    def test_archive_mode_blocks_lore_item_extraction_review_page(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/lore-items/extractions")

        self.assertEqual(response.status_code, 404)


class OpenThreadRouteTest(unittest.TestCase):
    def thread_rows(self):
        return [{
            "id": 1,
            "title": "What does the Gale want?",
            "thread_type": "lore_mystery",
            "status": "open",
            "first_session": 20,
            "last_session": None,
            "related_location": "The Gale",
            "description": "The Gale may be more than weather.",
            "resolution": "",
            "notes": "Connects to the coast near Catur.",
        }]

    def locations(self):
        return [{"id": 3, "name": "The Gale"}]

    def extraction(self):
        return {
            "path": Path("/tmp/session21_open_threads.json"),
            "known_thread_mentions": [{
                "thread_id": 1,
                "canonical_title": "What does the Gale want?",
                "new_information": "The Gale remains an unvisited danger.",
                "thread_type": "active_threat",
                "status": "open",
                "first_session": 20,
                "last_session": 21,
                "related_location": "The Gale",
                "resolution": "",
                "confidence": "high",
                "evidence": "The Gale remains ahead.",
            }],
            "new_thread_candidates": [{
                "proposed_title": "Niebain Warns Catur Is Already In Danger",
                "thread_type": "active_threat",
                "status": "open",
                "first_session": 21,
                "last_session": 21,
                "related_location": "Catur",
                "description": "Niebain warned that Catur was already in danger.",
                "resolution": "",
                "notes": "Name spelling uncertain.",
                "confidence": "high",
                "evidence": "We are in great danger already.",
            }],
            "rejected_candidates": [{"text": "Faban hates boats", "reason": "Character color."}],
            "uncertainties": [{"candidate": "Niebain / Nebain", "issue": "Spelling uncertain."}],
        }

    def test_open_threads_page_renders_sidebar_and_ledger(self):
        with patch("web_review.services.canon.open_thread_rows", return_value=self.thread_rows()), \
             patch("web_review.services.canon.location_rows", return_value=self.locations()):
            client = TestClient(app)
            response = client.get("/open-threads")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Open Threads", response.text)
        self.assertIn("What does the Gale want?", response.text)
        self.assertIn("lore mystery", response.text)
        self.assertIn("The Gale", response.text)
        self.assertIn('href="/open-threads"', response.text)
        self.assertIn("Add New", response.text)
        self.assertIn("<th>State</th>", response.text)
        self.assertIn("<th>Scope</th>", response.text)
        self.assertIn("/static/open-threads-icon.png", response.text)
        self.assertIn('href="/open-threads/1/edit"', response.text)
        self.assertIn('action="/open-threads/1/delete"', response.text)
        self.assertIn('aria-label="Edit What does the Gale want?"', response.text)
        self.assertIn('aria-label="Delete What does the Gale want?"', response.text)
        self.assertIn('href="/open-threads/extractions"', response.text)
        self.assertNotIn("Add Open Thread</h2>", response.text)

    def test_open_threads_add_modal_renders_four_statuses(self):
        with patch("web_review.services.canon.open_thread_rows", return_value=self.thread_rows()), \
             patch("web_review.services.canon.location_rows", return_value=self.locations()):
            client = TestClient(app)
            response = client.get("/open-threads?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Open Thread", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn('value="open"', response.text)
        self.assertIn('value="resolved"', response.text)
        self.assertIn('value="superseded"', response.text)
        self.assertIn('value="unknown"', response.text)

    def test_archive_mode_hides_open_thread_edit_controls(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.canon.open_thread_rows", return_value=self.thread_rows()), \
             patch("web_review.services.canon.location_rows", return_value=self.locations()):
            client = TestClient(app)
            response = client.get("/open-threads?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Open Threads", response.text)
        self.assertNotIn("Add New", response.text)
        self.assertNotIn('aria-label="Edit What does the Gale want?"', response.text)
        self.assertNotIn('aria-label="Delete What does the Gale want?"', response.text)
        self.assertNotIn("workflow-detail-modal", response.text)

    def test_create_open_thread_route_writes_form_values(self):
        with patch("web_review.services.canon.create_open_thread") as create:
            client = TestClient(app)
            response = client.post("/open-threads", data={
                "title": "What does the Gale want?",
                "thread_type": "lore_mystery",
                "status": "open",
                "first_session": "20",
                "last_session": "",
                "related_location_id": "3",
                "description": "The Gale may be more than weather.",
                "resolution": "",
                "notes": "Connects to the coast near Catur.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("created=1", response.headers["location"])
        create.assert_called_once()
        values = create.call_args.args[0]
        self.assertEqual(values["title"], "What does the Gale want?")
        self.assertEqual(values["thread_type"], "lore_mystery")
        self.assertEqual(values["status"], "open")
        self.assertEqual(values["first_session"], 20)
        self.assertIsNone(values["last_session"])
        self.assertEqual(values["related_location_id"], 3)

    def test_create_open_thread_merges_existing_title(self):
        values = {
            "title": "The Elemental Influence on the Monastery",
            "thread_type": "faction_tension",
            "status": "open",
            "first_session": 23,
            "last_session": 23,
            "related_location_id": 922,
            "description": "The monastery's elemental influence remains unclear.",
            "resolution": "",
            "notes": "Session 23 evidence.",
        }
        with patch("web_review.db.execute") as execute:
            canon.create_open_thread(values)

        sql = execute.call_args.args[0]
        self.assertIn("ON CONFLICT (title) DO UPDATE", sql)
        self.assertIn("WHEN open_thread.status <> 'open' THEN open_thread.status", sql)
        self.assertIn("POSITION(EXCLUDED.notes IN open_thread.notes)", sql)

    def test_edit_open_thread_page_loads_thread(self):
        detail = {
            "id": 1,
            "title": "What does the Gale want?",
            "thread_type": "lore_mystery",
            "status": "open",
            "first_session": 20,
            "last_session": None,
            "related_location_id": 3,
            "description": "The Gale may be more than weather.",
            "resolution": "",
            "notes": "Connects to the coast near Catur.",
        }
        with patch("web_review.services.canon.open_thread_rows", return_value=self.thread_rows()), \
             patch("web_review.services.canon.location_rows", return_value=self.locations()), \
             patch("web_review.services.canon.open_thread_detail", return_value=detail):
            client = TestClient(app)
            response = client.get("/open-threads/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Edit Open Thread", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn("The Gale may be more than weather.", response.text)

    def test_update_open_thread_route_writes_form_values(self):
        with patch("web_review.services.canon.update_open_thread") as update:
            client = TestClient(app)
            response = client.post("/open-threads/3", data={
                "title": "What does the Gale want?",
                "thread_type": "dm_foreshadowing",
                "status": "resolved",
                "first_session": "20",
                "last_session": "21",
                "related_location_id": "",
                "description": "Settled by later revelation.",
                "resolution": "The party learned the answer.",
                "notes": "",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("updated=1", response.headers["location"])
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], 3)
        self.assertEqual(update.call_args.args[1]["thread_type"], "dm_foreshadowing")
        self.assertEqual(update.call_args.args[1]["status"], "resolved")
        self.assertEqual(update.call_args.args[1]["last_session"], 21)

    def test_delete_open_thread_route_runs_delete(self):
        with patch("web_review.services.canon.delete_open_thread") as delete:
            client = TestClient(app)
            response = client.post("/open-threads/4/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("deleted=1", response.headers["location"])
        delete.assert_called_once_with(4)

    def test_open_thread_extraction_review_page_renders_decisions(self):
        with patch.object(open_thread_extraction_review, "available_sessions", return_value=[20, 21]), \
             patch.object(open_thread_extraction_review, "load_extraction", return_value=self.extraction()), \
             patch.object(open_thread_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session21_open_threads_reviewed.json")):
            client = TestClient(app)
            response = client.get("/open-threads/extractions?session=21")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Open Thread Extraction Review", response.text)
        self.assertIn("What does the Gale want?", response.text)
        self.assertIn("Niebain Warns Catur Is Already In Danger", response.text)
        self.assertIn('name="known_decision_0"', response.text)
        self.assertIn('name="new_decision_0"', response.text)

    def test_apply_open_thread_extraction_review_posts_decisions(self):
        result = {"applied": ["Created Niebain Warns Catur Is Already In Danger"], "skipped": ["Ignored What does the Gale want?"], "reviewed_path": Path("/tmp/reviewed.json")}
        with patch.object(open_thread_extraction_review, "apply_review", return_value=result) as apply_review, \
             patch("web_review.services.workflow.sync_session_workflow") as sync:
            client = TestClient(app)
            response = client.post("/open-threads/extractions/apply", data={
                "session_number": "21",
                "known_decision_0": "ignore",
                "new_decision_0": "create",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/open-threads/extractions?session=21", response.headers["location"])
        apply_review.assert_called_once()
        self.assertEqual(apply_review.call_args.args[0], 21)
        self.assertEqual(apply_review.call_args.args[1]["new_decision_0"], "create")
        sync.assert_called_once_with(21)

    def test_archive_mode_blocks_open_thread_extraction_review_page(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/open-threads/extractions")

        self.assertEqual(response.status_code, 404)


class CombatEncounterRouteTest(unittest.TestCase):
    def combat_rows(self):
        return [{
            "id": 1,
            "session_number": 19,
            "session_title": "Of Teeth, Memory, and What Remains",
            "session_span": "Session 19",
            "title": "Orsydon summoned in Balrog",
            "subtype": "dragon_summoning",
            "location": "Balrog",
            "participants": "Party, Orsydon, cultists",
            "outcome": "dragon_defeated",
            "confidence": "high",
            "notes": "Cultists summon Orsydon in Balrog.",
            "known_enemy_total": 6,
            "has_unknown_quantity": False,
            "enemies": [
                {
                    "name": "Orsydon",
                    "enemy_type": "dragon",
                    "quantity": 1,
                    "quantity_killed": 0,
                    "outcome": "defeated",
                    "confidence": "high",
                    "notes": "Dragon defeated.",
                },
                {
                    "name": "Cultist spellcaster",
                    "enemy_type": "cultist_spellcaster",
                    "quantity": 2,
                    "quantity_killed": 2,
                    "outcome": "killed",
                    "confidence": "high",
                    "notes": "Both killed.",
                },
                {
                    "name": "Cultist melee fighter",
                    "enemy_type": "cultist_melee",
                    "quantity": 3,
                    "quantity_killed": 3,
                    "outcome": "killed",
                    "confidence": "high",
                    "notes": "All killed.",
                },
            ],
        }]

    def test_combat_encounters_page_renders_ledger_and_murder_hobo_count(self):
        with patch("web_review.services.canon.combat_encounter_rows", return_value=self.combat_rows()), \
             patch("web_review.services.canon.session_rows", return_value=[{"session_number": 19, "title": "Of Teeth, Memory, and What Remains"}]), \
             patch("web_review.services.canon.location_rows", return_value=[{"id": 4, "name": "Balrog"}]), \
             patch("web_review.services.canon.lookup_rows", return_value=[{"value": "killed", "description": "Enemy was killed."}]):
            client = TestClient(app)
            response = client.get("/combat-encounters")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Combat Encounters", response.text)
        self.assertIn("Orsydon summoned in Balrog", response.text)
        self.assertIn("Murder Hobo Count", response.text)
        self.assertIn(">5<", response.text)
        self.assertIn("Battle Locale", response.text)
        self.assertIn('aria-label="Edit Orsydon summoned in Balrog"', response.text)
        self.assertIn('href="/combat-encounters"', response.text)
        self.assertIn("/static/combat-encounters-icon.png", response.text)

    def test_combat_encounters_add_modal_renders_crud_form(self):
        with patch("web_review.services.canon.combat_encounter_rows", return_value=self.combat_rows()), \
             patch("web_review.services.canon.session_rows", return_value=[{"session_number": 19, "title": "Of Teeth, Memory, and What Remains"}]), \
             patch("web_review.services.canon.location_rows", return_value=[{"id": 4, "name": "Balrog"}]), \
             patch("web_review.services.canon.lookup_rows", return_value=[{"value": "killed", "description": "Enemy was killed."}]):
            client = TestClient(app)
            response = client.get("/combat-encounters?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Combat Encounter", response.text)
        self.assertIn("+ Add Enemy", response.text)
        self.assertIn('name="enemy_name_1"', response.text)
        self.assertIn('name="enemy_quantity_1"', response.text)
        self.assertIn('name="enemy_quantity_killed_1"', response.text)

    def test_archive_mode_hides_combat_encounter_edit_controls(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.canon.combat_encounter_rows", return_value=self.combat_rows()), \
             patch("web_review.services.canon.session_rows", return_value=[{"session_number": 19, "title": "Of Teeth, Memory, and What Remains"}]), \
             patch("web_review.services.canon.location_rows", return_value=[{"id": 4, "name": "Balrog"}]), \
             patch("web_review.services.canon.lookup_rows", return_value=[{"value": "killed", "description": "Enemy was killed."}]):
            client = TestClient(app)
            response = client.get("/combat-encounters?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Add New", response.text)
        self.assertNotIn('aria-label="Edit Orsydon summoned in Balrog"', response.text)

    def test_create_combat_encounter_route_writes_parent_and_enemy_rows(self):
        with patch("web_review.services.canon.create_combat_encounter") as create:
            client = TestClient(app)
            response = client.post("/combat-encounters", data={
                "session_number": "19",
                "title": "Orsydon summoned in Balrog",
                "subtype": "dragon_summoning",
                "location_id": "4",
                "participants": "Party, Orsydon, cultists",
                "outcome": "enemies_defeated",
                "confidence": "high",
                "notes": "Cultists summon Orsydon.",
                "enemy_name_1": "Orsydon",
                "enemy_type_1": "dragon",
                "enemy_quantity_1": "1",
                "enemy_quantity_killed_1": "0",
                "enemy_outcome_1": "defeated",
                "enemy_confidence_1": "high",
                "enemy_notes_1": "Dragon defeated.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("created=1", response.headers["location"])
        values, enemies = create.call_args.args
        self.assertEqual(values["session_number"], 19)
        self.assertEqual(values["location_id"], 4)
        self.assertEqual(enemies[0]["name"], "Orsydon")
        self.assertEqual(enemies[0]["quantity"], 1)
        self.assertEqual(enemies[0]["quantity_killed"], 0)

    def test_edit_combat_encounter_page_loads_detail(self):
        detail = {
            "id": 1,
            "session_number": 19,
            "event_id": 99,
            "title": "Orsydon summoned in Balrog",
            "subtype": "dragon_summoning",
            "location_id": 4,
            "participants": "Party, Orsydon, cultists",
            "outcome": "enemies_defeated",
            "confidence": "high",
            "notes": "Cultists summon Orsydon.",
            "enemies": [{"name": "Orsydon", "enemy_type": "dragon", "quantity": 1, "quantity_killed": 0, "outcome": "defeated", "confidence": "high", "notes": "Dragon defeated."}],
        }
        with patch("web_review.services.canon.combat_encounter_rows", return_value=self.combat_rows()), \
             patch("web_review.services.canon.session_rows", return_value=[{"session_number": 19, "title": "Of Teeth, Memory, and What Remains"}]), \
             patch("web_review.services.canon.location_rows", return_value=[{"id": 4, "name": "Balrog"}]), \
             patch("web_review.services.canon.lookup_rows", return_value=[{"value": "killed", "description": "Enemy was killed."}]), \
             patch("web_review.services.canon.combat_encounter_detail", return_value=detail):
            client = TestClient(app)
            response = client.get("/combat-encounters/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Edit Combat Encounter", response.text)
        self.assertIn("Dragon defeated.", response.text)

    def test_update_combat_encounter_route_writes_values(self):
        with patch("web_review.services.canon.update_combat_encounter") as update:
            client = TestClient(app)
            response = client.post("/combat-encounters/1", data={
                "session_number": "19",
                "title": "Orsydon summoned in Balrog",
                "location_id": "4",
                "outcome": "enemies_defeated",
                "confidence": "high",
                "enemy_name_1": "Cultist",
                "enemy_quantity_1": "",
                "enemy_quantity_killed_1": "1",
                "enemy_outcome_1": "killed",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("updated=1", response.headers["location"])
        self.assertEqual(update.call_args.args[0], 1)
        self.assertIsNone(update.call_args.args[2][0]["quantity"])
        self.assertEqual(update.call_args.args[2][0]["quantity_killed"], 1)

    def test_update_combat_encounter_route_skips_removed_enemy_rows(self):
        with patch("web_review.services.canon.update_combat_encounter") as update:
            client = TestClient(app)
            response = client.post("/combat-encounters/1", data={
                "session_number": "19",
                "title": "Orsydon summoned in Balrog",
                "outcome": "enemies_defeated",
                "confidence": "high",
                "enemy_name_1": "Orsydon",
                "enemy_quantity_1": "1",
                "enemy_quantity_killed_1": "0",
                "enemy_outcome_1": "defeated",
                "enemy_remove_1": "on",
                "enemy_name_2": "Cultist",
                "enemy_quantity_2": "5",
                "enemy_quantity_killed_2": "5",
                "enemy_outcome_2": "killed",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        enemies = update.call_args.args[2]
        self.assertEqual(len(enemies), 1)
        self.assertEqual(enemies[0]["name"], "Cultist")
        self.assertEqual(enemies[0]["quantity_killed"], 5)

    def test_delete_combat_encounter_route_runs_delete(self):
        with patch("web_review.services.canon.delete_combat_encounter") as delete:
            client = TestClient(app)
            response = client.post("/combat-encounters/1/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("deleted=1", response.headers["location"])
        delete.assert_called_once_with(1)

    def combat_extraction(self):
        return {
            "path": Path("/tmp/session19_combat_encounters.json"),
            "proposed_combat_encounters": [{
                "title": "Orsydon summoned in Balrog",
                "session_number": 19,
                "subtype": "dragon_summoning",
                "location": "Balrog",
                "participants": "Party, Orsydon, cultists",
                "outcome": "enemies_defeated",
                "confidence": "high",
                "notes": "Cultists summoned Orsydon.",
                "evidence": "Cultists summoned the dragon Orsydon.",
                "enemies": [{"name": "Orsydon", "enemy_type": "dragon", "quantity": 1, "quantity_killed": 0, "outcome": "defeated"}],
            }],
            "rejected_candidates": [{"text": "Audience", "reason": "Social encounter."}],
            "uncertainties": [{"candidate": "Cultists", "issue": "Quantity unclear."}],
        }

    def test_combat_extraction_review_page_renders_proposed_encounters(self):
        with patch.object(combat_extraction_review, "available_sessions", return_value=[19]), \
             patch.object(combat_extraction_review, "load_extraction", return_value=self.combat_extraction()), \
             patch.object(combat_extraction_review, "reviewed_output_path", return_value=Path("/tmp/session19_combat_encounters_reviewed.json")):
            client = TestClient(app)
            response = client.get("/combat-encounters/extractions?session=19")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Combat Extraction Review", response.text)
        self.assertIn("Orsydon summoned in Balrog", response.text)
        self.assertIn('name="encounter_decision_0"', response.text)
        self.assertIn("Orsydon", response.text)

    def test_apply_combat_extraction_review_posts_decisions(self):
        result = {"applied": ["Created Orsydon summoned in Balrog"], "skipped": [], "reviewed_path": Path("/tmp/reviewed.json")}
        with patch.object(combat_extraction_review, "apply_review", return_value=result) as apply_review, \
             patch("web_review.services.workflow.sync_session_workflow") as sync:
            client = TestClient(app)
            response = client.post("/combat-encounters/extractions/apply", data={
                "session_number": "19",
                "encounter_decision_0": "create",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/combat-encounters/extractions?session=19", response.headers["location"])
        apply_review.assert_called_once()
        self.assertEqual(apply_review.call_args.args[0], 19)
        self.assertEqual(apply_review.call_args.args[1]["encounter_decision_0"], "create")
        sync.assert_called_once_with(19)

    def test_archive_mode_blocks_combat_extraction_review_page(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/combat-encounters/extractions")

        self.assertEqual(response.status_code, 404)

    def test_combat_encounters_api_returns_rows(self):
        with patch("web_review.services.canon.combat_encounter_rows", return_value=self.combat_rows()):
            client = TestClient(app)
            response = client.get("/api/combat-encounters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["enemies"][1]["quantity"], 2)


class CampaignTimelineRouteTest(unittest.TestCase):
    def timeline(self):
        return {
            "stats": {
                "session_count": 2,
                "total_travel_days": 4,
                "known_travel_segments": 1,
                "first_in_game_date": "1832 AS Apollal 10",
                "latest_in_game_date": "1832 AS Namal 24",
                "current_location": "Coast near Catur",
            },
            "rows": [
                {
                    "session_number": 0,
                    "session_label": "Session 00",
                    "session_date": "2025-02-02",
                    "in_game_date": "1832 AS Apollal 10",
                    "title": "The Party forms",
                    "summary": "",
                    "primary_location": "Bentrios",
                    "start_location": "Alexander's Inn",
                    "end_location": "Bentrios",
                    "travel": [],
                    "key_events": [
                        {
                            "event_type": "social",
                            "location": "Alexander's Inn",
                            "description": "The party begins to form at Alexander's Inn.",
                            "significance": 4,
                        },
                    ],
                    "event_count": 1,
                },
                {
                    "session_number": 20,
                    "session_label": "Session 20",
                    "session_date": "2026-04-27",
                    "in_game_date": "1832 AS Namal 20, 1832 AS Namal 24",
                    "in_game_date_display": "1832 AS Namal 20 thru 1832 AS Namal 24",
                    "title": "Salt, Steel, and the Distance Between Legends",
                    "summary": "",
                    "primary_location": "Coast near Catur",
                    "start_location": "Balrog",
                    "end_location": "Coast near Catur",
                    "travel": [
                        {
                            "from_location": "Balrog",
                            "to_location": "Coast near Catur",
                            "travel_method": "foot",
                            "duration_days": 4,
                            "duration_confidence": "high",
                            "duration_basis": "Diary dates span Namal 20 to Namal 24.",
                            "notes": "",
                        },
                    ],
                    "key_events": [],
                    "event_count": 0,
                },
            ],
        }

    def test_campaign_timeline_page_renders_timeline(self):
        with patch("web_review.services.canon.campaign_timeline", return_value=self.timeline()):
            client = TestClient(app)
            response = client.get("/timeline")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Campaign Timeline", response.text)
        self.assertIn("Known Travel Days", response.text)
        self.assertIn("/static/timeline-sessions-icon.png", response.text)
        self.assertIn("/static/timeline-travel-icon.png", response.text)
        self.assertIn("/static/timeline-location-icon.png", response.text)
        self.assertIn("campaign-flow", response.text)
        self.assertIn('class="session-orb"', response.text)
        self.assertIn('href="#session-20-modal"', response.text)
        self.assertIn('title="Session 20: Salt, Steel, and the Distance Between Legends"', response.text)
        self.assertIn('data-tooltip="Session 20: Salt, Steel, and the Distance Between Legends"', response.text)
        self.assertIn('id="session-20-modal"', response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn("1832 AS Namal 20 thru 1832 AS Namal 24", response.text)
        self.assertIn("Starting Location", response.text)
        self.assertIn("Ending Location", response.text)
        self.assertNotIn(">1832 AS Namal 20, 1832 AS Namal 24<", response.text)
        self.assertIn("Balrog -> Coast near Catur", response.text)
        self.assertIn("The party begins to form", response.text)
        self.assertIn('href="/timeline"', response.text)

    def test_campaign_timeline_api_returns_rows(self):
        with patch("web_review.services.canon.campaign_timeline", return_value=self.timeline()):
            client = TestClient(app)
            response = client.get("/api/timeline")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stats"]["current_location"], "Coast near Catur")
        self.assertEqual(response.json()["rows"][1]["travel"][0]["duration_days"], 4)


class ProjectUtilitiesRouteTest(unittest.TestCase):
    def setUp(self):
        COMMAND_RESULTS.clear()
        BACKUP_DOWNLOADS.clear()

    def test_project_utilities_page_renders_todo_viewer(self):
        with patch("web_review.services.workflow.next_session_number", return_value=21):
            client = TestClient(app)
            response = client.get("/project-utilities")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Project Utilities", response.text)
        self.assertIn("View Todo", response.text)
        self.assertIn("Backup Database", response.text)
        self.assertIn("Run Smoke Test", response.text)
        self.assertIn("Export Static Archive", response.text)
        self.assertIn("Publish Static Archive", response.text)
        self.assertIn("Lookup Tables", response.text)
        self.assertIn("Initiate Session", response.text)
        self.assertIn('href="/project-utilities/lookups"', response.text)
        self.assertIn('href="/project-utilities?modal=initiate-session"', response.text)
        self.assertIn("/static/project-utilities-icon.png", response.text)
        self.assertIn("todo.md", response.text)
        self.assertIn('href="/project-utilities"', response.text)

    def test_project_utilities_session_initiation_modal_renders_defaults(self):
        with patch("web_review.services.workflow.next_session_number", return_value=21):
            client = TestClient(app)
            response = client.get("/project-utilities?modal=initiate-session")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Initiate Session Workflow", response.text)
        self.assertIn('name="session_number"', response.text)
        self.assertIn('value="21"', response.text)
        self.assertIn('name="audio_file_path"', response.text)
        self.assertIn('name="transcript_policy"', response.text)
        self.assertIn('value="use_existing" checked', response.text)
        self.assertIn('value="recreate"', response.text)
        self.assertIn("/project-utilities/initiate-session", response.text)

    def test_project_utilities_session_initiation_posts_to_workflow(self):
        with patch("web_review.services.workflow.initiate_session", return_value=21) as initiate, \
             patch("web_review.services.workflow.enqueue_auto_intake", return_value=None) as enqueue:
            client = TestClient(app)
            response = client.post(
                "/project-utilities/initiate-session",
                data={
                    "session_number": "21",
                    "session_date": "2026-05-17",
                    "title": "Storm over Catur",
                    "audio_file_path": "/tmp/session21.wav",
                    "transcript_policy": "recreate",
                    "notes": "Fresh session.",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/workflow?session=21")
        initiate.assert_called_once_with({
            "session_number": "21",
            "session_date": "2026-05-17",
            "title": "Storm over Catur",
            "audio_file_path": "/tmp/session21.wav",
            "transcript_policy": "recreate",
            "notes": "Fresh session.",
        })
        enqueue.assert_called_once_with(21, "recreate")

    def lookup_context_patches(self, editing=None):
        return (
            patch("web_review.services.canon.lookup_definitions", return_value=[
                {"key": "artifact-types", "label": "Artifact Types", "description_column": None},
                {"key": "combat-outcomes", "label": "Combat Outcomes", "description_column": "description"},
            ]),
            patch("web_review.services.canon.lookup_definition", return_value={
                "key": "combat-outcomes",
                "label": "Combat Outcomes",
                "table": "combat_outcome",
                "value_column": "outcome_code",
                "description_column": "description",
            }),
            patch("web_review.services.canon.lookup_rows", return_value=[
                {"id": 1, "value": "defeated", "description": "Enemy was overcome."},
            ]),
            patch("web_review.services.canon.lookup_detail", return_value=editing),
        )

    def test_lookup_tables_page_renders_active_table(self):
        definition, active, rows, detail = self.lookup_context_patches()
        with definition, active, rows, detail:
            client = TestClient(app)
            response = client.get("/project-utilities/lookups?table=combat-outcomes")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Lookup Tables", response.text)
        self.assertIn("Combat Outcomes", response.text)
        self.assertIn("defeated", response.text)
        self.assertIn("Enemy was overcome.", response.text)
        self.assertIn('href="/project-utilities/lookups?table=artifact-types"', response.text)

    def test_lookup_tables_add_modal_renders_form(self):
        definition, active, rows, detail = self.lookup_context_patches()
        with definition, active, rows, detail:
            client = TestClient(app)
            response = client.get("/project-utilities/lookups?table=combat-outcomes&modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Combat Outcomes", response.text)
        self.assertIn('name="value"', response.text)
        self.assertIn('name="description"', response.text)

    def test_lookup_tables_edit_modal_loads_row(self):
        definition, active, rows, detail = self.lookup_context_patches(
            {"id": 1, "value": "defeated", "description": "Enemy was overcome."}
        )
        with definition, active, rows, detail:
            client = TestClient(app)
            response = client.get("/project-utilities/lookups/combat-outcomes/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Edit Combat Outcomes", response.text)
        self.assertIn("Enemy was overcome.", response.text)

    def test_create_lookup_value_route_writes_form_values(self):
        with patch("web_review.services.canon.create_lookup_value") as create:
            client = TestClient(app)
            response = client.post(
                "/project-utilities/lookups/combat-outcomes",
                data={"value": "banished", "description": "Sent away."},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("created=1", response.headers["location"])
        create.assert_called_once_with("combat-outcomes", "banished", "Sent away.")

    def test_update_lookup_value_route_writes_form_values(self):
        with patch("web_review.services.canon.update_lookup_value") as update:
            client = TestClient(app)
            response = client.post(
                "/project-utilities/lookups/combat-outcomes/4",
                data={"value": "banished", "description": "Sent away."},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("updated=1", response.headers["location"])
        update.assert_called_once_with("combat-outcomes", 4, "banished", "Sent away.")

    def test_delete_lookup_value_route_runs_delete(self):
        with patch("web_review.services.canon.delete_lookup_value") as delete:
            client = TestClient(app)
            response = client.post("/project-utilities/lookups/combat-outcomes/4/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("deleted=1", response.headers["location"])
        delete.assert_called_once_with("combat-outcomes", 4)

    def test_project_utilities_page_renders_revision_viewer(self):
        with patch("web_review.services.workflow.next_session_number", return_value=21):
            client = TestClient(app)
            response = client.get("/project-utilities?document=revision")

        self.assertEqual(response.status_code, 200)
        self.assertIn("revision.md", response.text)
        self.assertIn("Revision History", response.text)

    def test_archive_mode_hides_project_utilities(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}):
            client = TestClient(app)
            response = client.get("/project-utilities")

        self.assertEqual(response.status_code, 404)

    def test_backup_route_creates_download_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_path = Path(tmp) / "farrlind_test.sql"
            backup_path.write_text("-- backup", encoding="utf-8")
            with patch("web_review.app.backup_database", return_value=backup_path):
                client = TestClient(app)
                response = client.post("/project-utilities/backup", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("backup=", response.headers["location"])
        self.assertEqual(len(BACKUP_DOWNLOADS), 1)

    def test_smoke_test_route_reports_result(self):
        with patch("web_review.services.commands.run_smoke_test", return_value=commands.CommandResult(0, "Smoke test passed.", "")) as smoke:
            client = TestClient(app)
            response = client.post("/project-utilities/smoke-test", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("command_result=", response.headers["location"])
        smoke.assert_called_once()

    def test_static_export_route_reports_result(self):
        with patch("web_review.services.commands.run_static_export", return_value=commands.CommandResult(0, "Static archive exported.", "")) as export:
            client = TestClient(app)
            response = client.post("/project-utilities/export-static-archive", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("command_result=", response.headers["location"])
        export.assert_called_once()

    def test_static_publish_route_reports_result(self):
        with patch("web_review.services.commands.publish_static_archive", return_value=commands.CommandResult(0, "Static archive committed.", "")) as publish:
            client = TestClient(app)
            response = client.post("/project-utilities/publish-static-archive", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("command_result=", response.headers["location"])
        publish.assert_called_once_with(
            base_url="http://web_archive:8000",
            static_repo="",
            push=False,
        )


class SongbookRouteTest(unittest.TestCase):
    def song_rows(self):
        return [{
            "id": 1,
            "song_number": 1,
            "order_number": 1,
            "title": "The Off-Key Dragon",
            "style_id": 1,
            "style": "tavern_song",
            "category_id": 1,
            "category": "humor",
            "song_type": "Comic tavern song",
            "short_description": "Tavern comedy",
            "long_description": "A ridiculous tale of a dragon whose singing voice is worse than its fire.",
            "summary": "",
            "suno_prompt": "",
            "musical_key": "G major",
            "meter": "6/8",
            "tempo": "120 BPM",
            "instrumentation": "fiddle and drum",
            "lyrics_local_path": "knowledge/Faban/songbook/The_Off_Key_Dragon/lyrics.md",
            "mp3_local_path": "knowledge/Faban/songbook/The_Off_Key_Dragon/song.mp3",
            "mp3_url": "https://example.com/audio",
            "lyrics_url": "https://example.com/lyrics",
            "written_session": None,
            "in_world_context": "",
            "is_performed": True,
            "has_local_audio": True,
            "has_local_lyrics": True,
        }]

    def test_songbook_page_renders_cards_and_audio_controls(self):
        foreword = {"title": "The Revealed Songbook", "text": "A bard's duty is to remember.", "path": "", "notes": ""}
        with patch("web_review.services.canon.songbook_rows", return_value=self.song_rows()), \
             patch("web_review.services.canon.songbook_foreword", return_value=foreword):
            client = TestClient(app)
            response = client.get("/songbook")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Faban", response.text)
        self.assertIn("The Off-Key Dragon", response.text)
        self.assertIn("/songbook/1/audio", response.text)
        self.assertIn("/songbook/1/lyrics", response.text)
        self.assertIn('href="/songbook"', response.text)
        self.assertIn("/static/fabans-songbook-icon.png", response.text)
        self.assertIn("Read Faban", response.text)
        self.assertIn("A bard", response.text)
        self.assertIn('href="/songbook?modal=add"', response.text)
        self.assertIn('href="/songbook/1/edit"', response.text)
        self.assertIn("Order 1", response.text)

    def test_songbook_add_modal_uses_separate_order_number(self):
        foreword = {"title": "", "text": "", "path": "", "notes": ""}
        manifest = {
            "lyrics": [{"title": "Song - Test Ballad", "url": "https://docs.google.com/document/d/test/edit"}],
            "audio": [{"title": "27 - Test Ballad.mp3", "url": "https://drive.google.com/file/d/audio/view"}],
            "updated_at": "2026-06-06",
        }
        with patch("web_review.services.canon.songbook_rows", return_value=self.song_rows()), \
             patch("web_review.services.canon.songbook_foreword", return_value=foreword), \
             patch("web_review.services.canon.song_styles", return_value=[{"id": 1, "style_name": "ballad"}]), \
             patch("web_review.services.canon.song_categories", return_value=[{"id": 2, "category_name": "lore"}]), \
             patch("web_review.services.canon.next_song_number", return_value=27), \
             patch("web_review.services.canon.next_song_order_number", return_value=27), \
             patch("web_review.services.songbook_drive.drive_manifest", return_value=manifest):
            client = TestClient(app)
            response = client.get("/songbook?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Song Number", response.text)
        self.assertIn("Order Number", response.text)
        self.assertIn('name="song_number"', response.text)
        self.assertIn('name="order_number"', response.text)
        self.assertIn('name="lyrics_drive_url"', response.text)
        self.assertIn('name="mp3_drive_url"', response.text)
        self.assertIn("Song - Test Ballad", response.text)
        self.assertIn("27 - Test Ballad.mp3", response.text)

    def test_create_songbook_entry_posts_to_canon(self):
        with patch("web_review.services.canon.create_song") as create:
            client = TestClient(app)
            response = client.post(
                "/songbook",
                data={
                    "song_number": "27",
                    "order_number": "5",
                    "title": "The Test Ballad",
                    "style_id": "1",
                    "category_id": "2",
                    "lyrics_drive_url": "https://docs.google.com/document/d/drive-choice/edit",
                    "lyrics_url": "https://docs.google.com/document/d/manual/edit",
                    "mp3_drive_url": "https://drive.google.com/file/d/drive-audio/view",
                    "mp3_url": "https://drive.google.com/file/d/manual-audio/view",
                    "is_performed": "on",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/songbook?created=1")
        create.assert_called_once()
        values = create.call_args.args[0]
        self.assertEqual(values["song_number"], 27)
        self.assertEqual(values["order_number"], 5)
        self.assertEqual(values["title"], "The Test Ballad")
        self.assertEqual(values["lyrics_url"], "https://docs.google.com/document/d/drive-choice/edit")
        self.assertEqual(values["mp3_url"], "https://drive.google.com/file/d/drive-audio/view")

    def test_songbook_edit_modal_keeps_current_drive_url_option(self):
        foreword = {"title": "", "text": "", "path": "", "notes": ""}
        row = {**self.song_rows()[0], "lyrics_url": "https://docs.google.com/document/d/current/edit", "mp3_url": "https://drive.google.com/file/d/current-audio/view"}
        manifest = {"lyrics": [], "audio": [], "updated_at": "2026-06-06"}
        with patch("web_review.services.canon.songbook_rows", return_value=[row]), \
             patch("web_review.services.canon.songbook_foreword", return_value=foreword), \
             patch("web_review.services.canon.songbook_detail", return_value=row), \
             patch("web_review.services.canon.song_styles", return_value=[]), \
             patch("web_review.services.canon.song_categories", return_value=[]), \
             patch("web_review.services.canon.next_song_number", return_value=2), \
             patch("web_review.services.canon.next_song_order_number", return_value=2), \
             patch("web_review.services.songbook_drive.drive_manifest", return_value=manifest):
            client = TestClient(app)
            response = client.get("/songbook/1/edit")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Current saved file", response.text)
        self.assertIn("https://docs.google.com/document/d/current/edit", response.text)
        self.assertIn("https://drive.google.com/file/d/current-audio/view", response.text)

    def test_update_songbook_entry_preserves_song_number_identity(self):
        with patch("web_review.services.canon.songbook_detail", return_value=self.song_rows()[0]), \
             patch("web_review.services.canon.update_song") as update:
            client = TestClient(app)
            response = client.post(
                "/songbook/1",
                data={"order_number": "9", "title": "Renamed Dragon", "is_performed": "on"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 303)
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], 1)
        self.assertEqual(update.call_args.args[1]["song_number"], 1)
        self.assertEqual(update.call_args.args[1]["order_number"], 9)

    def test_move_songbook_entry_updates_order_not_identity(self):
        with patch("web_review.services.canon.move_song") as move:
            client = TestClient(app)
            response = client.post("/songbook/1/move", data={"direction": "down"}, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/songbook?reordered=1")
        move.assert_called_once_with(1, "down")

    def test_delete_songbook_entry_uses_song_number_identity(self):
        with patch("web_review.services.canon.delete_song") as delete:
            client = TestClient(app)
            response = client.post("/songbook/1/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/songbook?deleted=1")
        delete.assert_called_once_with(1)

    def test_songbook_api_returns_rows(self):
        with patch("web_review.services.canon.songbook_rows", return_value=self.song_rows()):
            client = TestClient(app)
            response = client.get("/api/songbook")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["title"], "The Off-Key Dragon")

    def test_song_lyrics_page_renders_lyrics_and_metadata(self):
        with patch("web_review.services.canon.songbook_detail", return_value=self.song_rows()[0]), \
             patch("web_review.services.canon.songbook_lyrics", return_value="# The Off-Key Dragon\n\nVerse one."):
            client = TestClient(app)
            response = client.get("/songbook/1/lyrics")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Verse one.", response.text)
        self.assertIn("Comic tavern song", response.text)
        self.assertIn("Back to Songbook", response.text)
        self.assertIn('href="https://example.com/lyrics"', response.text)
        self.assertIn("Source Doc", response.text)
        self.assertIn('href="https://example.com/audio"', response.text)
        self.assertIn("Source Audio", response.text)

    def test_song_audio_route_serves_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "song.mp3"
            path.write_bytes(b"fake mp3")
            with patch("web_review.services.canon.songbook_asset_path", return_value=path):
                client = TestClient(app)
                response = client.get("/songbook/1/audio")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")

    def test_songbook_routes_are_hidden_when_campaign_disables_songbook(self):
        with patch("web_review.app.campaign_feature_enabled", return_value=False):
            client = TestClient(app)
            index_response = client.get("/")
            songbook_response = client.get("/songbook")
            api_response = client.get("/api/songbook")

        self.assertEqual(songbook_response.status_code, 404)
        self.assertEqual(api_response.status_code, 404)
        self.assertNotIn('href="/songbook"', index_response.text)


class WorkflowServiceTest(unittest.TestCase):
    def test_next_session_number_reads_max_session(self):
        with patch("web_review.db.fetch_all", return_value=[{"next_session_number": 21}]) as fetch:
            loaded = workflow.next_session_number()

        self.assertEqual(loaded, 21)
        self.assertIn("MAX(session_number)", fetch.call_args.args[0])

    def test_initiate_session_seeds_workflow_and_audio_step(self):
        definition = {
            "workflow": {
                "id": "farrlind_session_canon",
                "version": 1,
                "display_name": "Farrlind Session Canon Workflow",
                "definition_format": "test",
                "scope": "per_session",
                "state_persistence": "database",
            },
            "steps": [{
                "id": "source_audio_registered",
                "display_name": "Source Audio Registered",
                "lane": "intake",
                "expected_inputs": ["audio/sessionXX.wav"],
                "expected_outputs": ["audio/sessionXX.wav"],
                "dependencies": [],
            }],
        }
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio, \
             patch("raglib.workflow_state.load_workflow_definition", return_value=definition), \
             patch("web_review.services.workflow._execute_transaction") as execute:
            loaded = workflow.initiate_session({
                "session_number": "21",
                "session_date": "2026-05-17",
                "title": "Storm over Catur",
                "audio_file_path": audio.name,
                "transcript_policy": "recreate",
                "notes": "Fresh session.",
            })

        self.assertEqual(loaded, 21)
        statements = execute.call_args.args[0]
        joined_sql = "\n".join(statement for statement, _ in statements)
        self.assertIn("CREATE TABLE IF NOT EXISTS workflow_run", joined_sql)
        self.assertIn("INSERT INTO workflow_run", joined_sql)
        self.assertIn("UPDATE session", joined_sql)
        self.assertIn("source_audio_registered", joined_sql)
        audio_step = next(params for _sql, params in statements if params.get("status") == "complete")
        self.assertEqual(audio_step["artifacts"], f'["{audio.name}"]')
        transcribe_step = next(params for _sql, params in statements if params.get("summary_comment") == "Auto-intake will recreate the raw transcript from registered source audio.")
        self.assertEqual(transcribe_step["inputs"], f'["{audio.name}"]')
        self.assertIn('"transcript_policy": "recreate"', transcribe_step["metadata"])

    def test_initiate_session_normalizes_repo_absolute_mp3_path_for_docker(self):
        definition = {
            "workflow": {
                "id": "farrlind_session_canon",
                "version": 1,
                "display_name": "Farrlind Session Canon Workflow",
                "definition_format": "test",
                "scope": "per_session",
                "state_persistence": "database",
            },
            "steps": [{
                "id": "source_audio_registered",
                "display_name": "Source Audio Registered",
                "lane": "intake",
                "expected_inputs": ["campaigns/{campaign}/audio/sessionXX.wav"],
                "expected_outputs": ["campaigns/{campaign}/audio/sessionXX.wav"],
                "dependencies": [],
            }],
        }
        host_path = "/Volumes/T7_WORK/AI_RAG/campaigns/trinyvale/audio/session01.mp3"
        with patch("raglib.workflow_state.load_workflow_definition", return_value=definition), \
             patch("web_review.services.workflow._execute_transaction") as execute:
            workflow.initiate_session({
                "session_number": "1",
                "session_date": "2026-05-22",
                "title": "Trinyvale Begins",
                "audio_file_path": host_path,
                "notes": "",
            })

        statements = execute.call_args.args[0]
        session_update = next(params for _sql, params in statements if params.get("title") == "Trinyvale Begins")
        self.assertEqual(session_update["audio_file_path"], "campaigns/trinyvale/audio/session01.mp3")
        transcribe_step = next(params for _sql, params in statements if params.get("summary_comment") == "Auto-intake will use an existing raw transcript if present.")
        self.assertEqual(transcribe_step["inputs"], '["campaigns/trinyvale/audio/session01.mp3"]')

    def test_initiate_session_discovers_existing_mp3_when_path_is_blank(self):
        definition = {
            "workflow": {
                "id": "farrlind_session_canon",
                "version": 1,
                "display_name": "Farrlind Session Canon Workflow",
                "definition_format": "test",
                "scope": "per_session",
                "state_persistence": "database",
            },
            "steps": [{
                "id": "source_audio_registered",
                "display_name": "Source Audio Registered",
                "lane": "intake",
                "expected_inputs": ["campaigns/{campaign}/audio/sessionXX.*"],
                "expected_outputs": ["campaigns/{campaign}/audio/sessionXX.*"],
                "dependencies": [],
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "campaigns" / "trinyvale" / "audio" / "session02.mp3"
            audio.parent.mkdir(parents=True)
            audio.write_text("audio", encoding="utf-8")
            with patch("raglib.workflow_state.load_workflow_definition", return_value=definition), \
                 patch("web_review.services.reviews.REPO_ROOT", root), \
                 patch("web_review.services.workflow.campaign.audio_dir", return_value=audio.parent), \
                 patch("web_review.services.workflow.campaign.raw_dir", return_value=root / "campaigns" / "trinyvale" / "raw"), \
                 patch("web_review.services.workflow.campaign.clean_dir", return_value=root / "campaigns" / "trinyvale" / "clean"), \
                 patch("web_review.services.workflow._execute_transaction") as execute:
                workflow.initiate_session({
                    "session_number": "2",
                    "session_date": "2026-05-22",
                    "title": "Trinyvale Continues",
                    "audio_file_path": "",
                    "notes": "",
                })

        statements = execute.call_args.args[0]
        session_update = next(params for _sql, params in statements if params.get("title") == "Trinyvale Continues")
        self.assertEqual(session_update["audio_file_path"], "campaigns/trinyvale/audio/session02.mp3")
        metadata = next(params for _sql, params in statements if params.get("summary_comment", "").startswith("Session workflow initiated"))
        self.assertIn('"audio_extension": ".mp3"', metadata["metadata"])

    def test_enqueue_auto_intake_writes_queue_file_for_registered_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_dir = root / "ops" / "workflow_queue"
            audio = root / "audio" / "session21.wav"
            audio.parent.mkdir(parents=True)
            audio.write_text("audio", encoding="utf-8")
            with patch("web_review.services.workflow.QUEUE_DIR", queue_dir), \
                 patch("web_review.services.reviews.REPO_ROOT", root), \
                patch("web_review.services.workflow._fetch", return_value=[{"audio_file_path": "audio/session21.wav"}]), \
                 patch("web_review.services.workflow._execute_transaction") as execute:
                queued = workflow.enqueue_auto_intake(21, "recreate")
            self.assertEqual(queued, queue_dir / "session21.json")
            payload = json.loads((queue_dir / "session21.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["session_number"], 21)
            self.assertEqual(payload["transcript_policy"], "recreate")
            self.assertEqual(payload["commands"], [
            "transcribe_audio",
            "source_status_check",
            "curate_transcript",
            "generate_narrative_summary",
            "extract_session_spine",
            "validate_session_spine",
            "extract_npcs",
                "extract_locations",
                "extract_artifacts",
                "extract_lore_items",
                "extract_combat_encounters",
                "extract_open_threads",
                "extract_events",
                "postextract_shortcut",
            ])
        execute.assert_called_once()

    def test_enqueue_auto_intake_skips_when_audio_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("web_review.services.workflow.QUEUE_DIR", Path(tmp) / "queue"), \
                 patch("web_review.services.reviews.REPO_ROOT", Path(tmp)), \
                 patch("web_review.services.workflow._fetch", return_value=[{"audio_file_path": "audio/session21.wav"}]), \
                 patch("web_review.services.workflow._execute_transaction") as execute:
                queued = workflow.enqueue_auto_intake(21)

        self.assertIsNone(queued)
        execute.assert_not_called()

    def test_enqueue_draft_rerun_writes_guarded_queue_from_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_dir = root / "ops" / "workflow_queue"
            raw = root / "campaigns" / "farrlind" / "raw"
            raw.mkdir(parents=True)
            (raw / "session21_transcript.txt").write_text("transcript", encoding="utf-8")
            with patch("web_review.services.workflow.QUEUE_DIR", queue_dir), \
                 patch("web_review.services.reviews.REPO_ROOT", root), \
                 patch("web_review.services.reviews.KNOWLEDGE_DIR", root / "campaigns" / "farrlind"), \
                 patch("web_review.services.reviews.FINAL_DIR", root / "campaigns" / "farrlind" / "final"), \
                 patch("web_review.services.workflow.campaign.raw_dir", return_value=raw), \
                 patch("web_review.services.workflow.campaign.active_campaign_name", return_value="farrlind"), \
                 patch("web_review.services.workflow._fetch", return_value=[{"id": 21}]), \
                 patch("web_review.services.workflow._execute_transaction") as execute:
                queued = workflow.enqueue_draft_rerun(21)

            self.assertEqual(queued, queue_dir / "session21_draft_rerun.json")
            payload = json.loads(queued.read_text(encoding="utf-8"))
            self.assertEqual(payload["job_type"], "draft_rerun")
            self.assertNotIn("transcribe_audio", payload["commands"])
            self.assertIn("extract_npcs", payload["commands"])
            self.assertTrue(payload["guard"]["never_overwrite_reviewed_entities"])
            execute.assert_called_once()

    def test_enqueue_draft_rerun_blocks_when_entity_review_is_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "campaigns" / "farrlind" / "raw"
            extracted = root / "campaigns" / "farrlind" / "extracted"
            raw.mkdir(parents=True)
            extracted.mkdir(parents=True)
            (raw / "session21_transcript.txt").write_text("transcript", encoding="utf-8")
            (extracted / "session21_npcs_reviewed.json").write_text("{}", encoding="utf-8")
            with patch("web_review.services.reviews.REPO_ROOT", root), \
                 patch("web_review.services.workflow.campaign.raw_dir", return_value=raw), \
                 patch("web_review.services.reviews.KNOWLEDGE_DIR", root / "campaigns" / "farrlind"), \
                 patch("web_review.services.reviews.FINAL_DIR", root / "campaigns" / "farrlind" / "final"), \
                 patch("web_review.services.workflow._execute_transaction") as execute:
                with self.assertRaises(workflow.WorkflowWriteError):
                    workflow.enqueue_draft_rerun(21)

            execute.assert_not_called()

    def test_workflow_rows_reads_aggregate_progress(self):
        rows = [{
            "session_number": 20,
            "session_title": "Salt, Steel",
            "workflow_id": "farrlind_session_canon",
            "workflow_version": 1,
            "status": "completed",
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Seeded.",
            "total_steps": 26,
            "complete_steps": 26,
            "not_applicable_steps": 0,
            "pending_steps": 0,
            "raw_pending_steps": 0,
            "blocked_steps": 0,
            "stale_steps": 0,
            "attention_count": 0,
            "progress_percent": 100,
            "next_step_name": None,
            "next_step_status": None,
        }]
        with patch("web_review.db.fetch_all", return_value=rows) as fetch:
            loaded = workflow.workflow_rows()

        self.assertEqual(loaded[0]["session_number"], 20)
        self.assertEqual(loaded[0]["progress_percent"], 100)
        self.assertEqual(loaded[0]["session_key"], "session20")
        self.assertEqual(loaded[0]["workflow_url"], "/workflow?session=20")
        self.assertFalse(loaded[0]["has_attention"])
        self.assertIn("DISTINCT ON", fetch.call_args.args[0])
        self.assertIn("workflow_run", fetch.call_args.args[0])
        self.assertIn("workflow_step_state", fetch.call_args.args[0])

    def test_workflow_rows_treats_not_applicable_as_complete_for_state(self):
        rows = [{
            "session_number": 20,
            "session_title": "Salt, Steel",
            "workflow_id": "farrlind_session_canon",
            "workflow_version": 1,
            "status": "partially_completed",
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Seeded.",
            "total_steps": 26,
            "complete_steps": 24,
            "not_applicable_steps": 2,
            "pending_steps": 0,
            "raw_pending_steps": 0,
            "blocked_steps": 0,
            "stale_steps": 0,
            "attention_count": 0,
            "progress_percent": 100,
            "next_step_name": None,
            "next_step_status": None,
        }]
        with patch("web_review.db.fetch_all", return_value=rows):
            loaded = workflow.workflow_rows()

        self.assertEqual(loaded[0]["status"], "completed")
        self.assertEqual(loaded[0]["progress_percent"], 100)

    def test_workflow_rows_pending_steps_use_unresolved_count(self):
        rows = [{
            "session_number": 21,
            "session_title": "The Road to Sunken Catur",
            "workflow_id": "farrlind_session_canon",
            "workflow_version": 2,
            "status": "partially_completed",
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Seeded.",
            "total_steps": 43,
            "complete_steps": 39,
            "not_applicable_steps": 0,
            "raw_pending_steps": 3,
            "pending_steps": 4,
            "blocked_steps": 0,
            "stale_steps": 1,
            "attention_count": 4,
            "progress_percent": 91,
            "next_step_name": "Draft Canon Packet With Gemma",
            "next_step_status": "pending",
        }]
        with patch("web_review.db.fetch_all", return_value=rows):
            loaded = workflow.workflow_rows()

        self.assertEqual(loaded[0]["pending_steps"], 4)
        self.assertEqual(loaded[0]["attention_count"], 4)
        self.assertTrue(loaded[0]["has_attention"])

    def test_workflow_detail_reads_run_and_ordered_steps(self):
        run = {
            "id": 9,
            "session_number": 20,
            "session_title": "Salt, Steel",
            "workflow_id": "farrlind_session_canon",
            "workflow_version": 1,
            "workflow_name": "Farrlind Session Canon Workflow",
            "status": "completed",
            "initiated_at": None,
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Seeded.",
            "metadata": {"seeded_history": True},
        }
        steps = [{
            "step_order": 1,
            "step_id": "source_audio_registered",
            "display_name": "Source Audio Registered",
            "lane": "intake",
            "status": "complete",
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Audio exists.",
            "inputs": ["campaigns/farrlind/audio/session20.wav"],
            "outputs": ["campaigns/farrlind/audio/session20.wav"],
            "dependencies": [],
            "gate": "operator_supplied",
            "rerun_policy": "safe",
            "canon_impact": "none",
            "command": None,
            "status_rules": {},
            "metadata": {},
        }]
        with patch("web_review.db.fetch_all", side_effect=[[run], steps]):
            loaded = workflow.workflow_detail(20)

        self.assertEqual(loaded["session_number"], 20)
        self.assertEqual(loaded["review_url"], "/sessions/session20/review")
        self.assertEqual(loaded["steps"][0]["step_id"], "source_audio_registered")
        self.assertEqual(loaded["major_status"][0]["label"], "Session Kickoff")
        self.assertEqual(loaded["major_status"][0]["status"], "complete")
        self.assertEqual(loaded["attention_items"], [])

    def test_major_status_reports_entity_reviews_and_session_completion(self):
        steps = {
            "source_audio_registered": {"status": "complete", "summary_comment": "Audio exists."},
            "transcribe_audio": {"status": "complete", "summary_comment": "Transcript written."},
            "curate_transcript": {"status": "complete"},
            "generate_narrative_summary": {"status": "complete"},
            "extract_session_spine": {"status": "complete"},
            "validate_session_spine": {"status": "complete"},
            "extract_npcs": {"status": "complete"},
            "extract_locations": {"status": "complete"},
            "extract_artifacts": {"status": "complete"},
            "extract_lore_items": {"status": "complete"},
            "extract_combat_encounters": {"status": "complete"},
            "extract_open_threads": {"status": "complete"},
            "extract_events": {"status": "complete"},
            "postextract_shortcut": {"status": "complete"},
            "review_npc_extraction": {"status": "complete", "summary_comment": "NPCs applied."},
            "review_location_extraction": {"status": "pending"},
            "review_artifact_extraction": {"status": "complete"},
            "review_lore_item_extraction": {"status": "complete"},
            "review_combat_encounter_extraction": {"status": "complete"},
            "review_open_thread_extraction": {"status": "complete"},
            "apply_review": {"status": "complete"},
            "write_final_summary": {"status": "complete"},
        }
        run = {
            "summary_comment": "Started.",
            "steps": [{"step_id": key, **value} for key, value in steps.items()],
        }

        items = workflow.major_status_items(run)
        by_label = {item["label"]: item for item in items}

        self.assertEqual(by_label["Session Kickoff"]["status"], "complete")
        self.assertEqual(by_label["NPC Review"]["display_status"], "review completed")
        self.assertEqual(by_label["Location Review"]["display_status"], "needs review")
        self.assertEqual(by_label["Session Ingest"]["status"], "pending")

    def test_workflow_detail_treats_not_applicable_as_complete_for_state(self):
        run = {
            "id": 9,
            "session_number": 20,
            "session_title": "Salt, Steel",
            "workflow_id": "farrlind_session_canon",
            "workflow_version": 1,
            "workflow_name": "Farrlind Session Canon Workflow",
            "status": "partially_completed",
            "initiated_at": None,
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Seeded.",
            "metadata": {},
        }
        steps = [
            {
                "step_order": 1,
                "step_id": "source_audio_registered",
                "display_name": "Source Audio Registered",
                "lane": "intake",
                "status": "complete",
                "started_at": None,
                "completed_at": None,
                "summary_comment": "Audio exists.",
                "inputs": [],
                "outputs": [],
                "dependencies": [],
                "gate": "operator_supplied",
                "rerun_policy": "safe",
                "canon_impact": "none",
                "command": None,
                "status_rules": {},
                "metadata": {},
            },
            {
                "step_order": 2,
                "step_id": "diary_source_available",
                "display_name": "Diary Source Available",
                "lane": "intake",
                "status": "not_applicable",
                "started_at": None,
                "completed_at": None,
                "summary_comment": "No diary source needed.",
                "inputs": [],
                "outputs": [],
                "dependencies": [],
                "gate": "operator_supplied",
                "rerun_policy": "safe",
                "canon_impact": "source_material",
                "command": None,
                "status_rules": {},
                "metadata": {},
            },
        ]
        with patch("web_review.db.fetch_all", side_effect=[[run], steps]):
            loaded = workflow.workflow_detail(20)

        self.assertEqual(loaded["status"], "completed")
        self.assertEqual(loaded["attention_items"], [])

    def test_sync_session_workflow_reseeds_single_session_from_artifacts(self):
        with patch("raglib.workflow_state.load_workflow_definition", return_value={
            "workflow": {"id": "farrlind_session_canon", "version": 1},
            "steps": [],
        }), \
             patch(
                 "raglib.workflow_state.historical_workflow_seed_sql",
                 return_value="UPDATE workflow_run SET summary_comment = 'one; two'; COMMIT;",
             ) as seed, \
             patch("web_review.services.workflow._execute_transaction") as execute:
            workflow.sync_session_workflow(1)

        seed.assert_called_once()
        self.assertEqual(seed.call_args.args[0:2], (1, 1))
        execute.assert_called_once()
        self.assertEqual(len(execute.call_args.args[0]), 2)
        self.assertIn("'one; two'", execute.call_args.args[0][0][0])

    def test_step_issues_surface_status_and_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "campaigns" / "farrlind" / "clean").mkdir(parents=True)
            (root / "campaigns" / "farrlind" / "clean" / "session21_diary.md").write_text("diary", encoding="utf-8")
            with patch("web_review.services.reviews.REPO_ROOT", root):
                issues = workflow.step_issues({
                    "status": "pending",
                    "summary_comment": "Waiting for transcript.",
                    "inputs": [
                        "campaigns/farrlind/clean/session21_diary.md",
                        "campaigns/farrlind/raw/session21_transcript.txt",
                    ],
                    "outputs": ["campaigns/farrlind/clean/session21_summary.md"],
                })

        self.assertIn("Waiting for transcript.", issues)
        self.assertIn("Missing input artifact campaigns/farrlind/raw/session21_transcript.txt.", issues)
        self.assertIn("Missing output artifact campaigns/farrlind/clean/session21_summary.md.", issues)

    def test_step_issues_ignore_optional_corrections_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("web_review.services.reviews.REPO_ROOT", Path(tmp)):
                issues = workflow.step_issues({
                    "status": "complete",
                    "summary_comment": "",
                    "inputs": ["campaigns/farrlind/notes/session20_corrections.md"],
                    "outputs": [],
                })

        self.assertEqual(issues, [])

    def test_step_links_route_review_and_registry_steps(self):
        self.assertEqual(
            workflow.step_links("edit_review_decisions", 20),
            [{"label": "Review Events", "url": "/sessions/session20/review"}],
        )
        self.assertEqual(
            workflow.step_links("review_npc_extraction", 20),
            [{"label": "Review NPCs", "url": "/npcs/extractions?session=20"}],
        )
        self.assertEqual(
            workflow.step_links("write_final_summary", 20),
            [{"label": "Final Summary", "url": "/sessions/session20/review?source=final&view=print"}],
        )
        self.assertEqual(
            workflow.step_links("update_lore_sections", 20),
            [
                {"label": "Lore Items", "url": "/lore-items"},
                {"label": "NPCs", "url": "/npcs"},
                {"label": "Locations", "url": "/locations"},
                {"label": "Artifacts", "url": "/artifacts"},
            ],
        )


class WorkflowRouteTest(unittest.TestCase):
    def workflow_rows(self):
        return [{
            "session_number": 20,
            "session_title": "Salt, Steel",
            "workflow_id": "farrlind_session_canon",
            "workflow_version": 1,
            "status": "completed",
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Seeded.",
            "total_steps": 26,
            "complete_steps": 26,
            "not_applicable_steps": 0,
            "pending_steps": 0,
            "blocked_steps": 0,
            "stale_steps": 0,
            "attention_count": 0,
            "progress_percent": 100,
            "next_step_name": None,
            "next_step_status": None,
            "session_key": "session20",
            "workflow_url": "/workflow?session=20",
        }]

    def workflow_detail(self):
        return {
            "id": 9,
            "session_number": 20,
            "session_title": "Salt, Steel",
            "workflow_id": "farrlind_session_canon",
            "workflow_version": 1,
            "workflow_name": "Farrlind Session Canon Workflow",
            "status": "completed",
            "initiated_at": None,
            "started_at": None,
            "completed_at": None,
            "summary_comment": "Seeded from historical chat workflow.",
            "metadata": {"seeded_history": True, "timestamp_estimate": True},
            "attention_items": [{
                "step": "Transcribe Audio",
                "issues": ["Missing output artifact knowledge/Faban/raw/session21_transcript.txt."],
            }],
            "session_key": "session20",
            "review_url": "/sessions/session20/review",
            "workflow_url": "/workflow?session=20",
            "can_rerun_draft": True,
            "draft_rerun_guard": {"allowed": True, "reasons": []},
            "steps": [{
                "step_order": 1,
                "step_id": "source_audio_registered",
                "display_name": "Source Audio Registered",
                "lane": "intake",
                "status": "complete",
                "started_at": "2026-05-17 19:43:00",
                "completed_at": "2026-05-17 19:44:00",
                "summary_comment": "Audio exists.",
                "inputs": ["audio/session20.wav"],
                "outputs": ["audio/session20.wav"],
                "dependencies": [],
                "gate": "operator_supplied",
                "rerun_policy": "safe",
                "canon_impact": "none",
                "command": None,
                "status_rules": {},
                "metadata": {},
                "links": [],
                "issues": [],
            }, {
                "step_order": 2,
                "step_id": "transcribe_audio",
                "display_name": "Transcribe Audio",
                "lane": "intake",
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "summary_comment": "Waiting for transcript.",
                "inputs": ["audio/session21.wav"],
                "outputs": ["knowledge/Faban/raw/session21_transcript.txt"],
                "dependencies": ["source_audio_registered"],
                "gate": "automatic_allowed_before_review",
                "rerun_policy": "safe_before_review",
                "canon_impact": "source_material",
                "command": "./rag-env/bin/python scripts/rag.py transcribe session21",
                "status_rules": {},
                "metadata": {},
                "links": [],
                "issues": ["Missing output artifact knowledge/Faban/raw/session21_transcript.txt."],
            }, {
                "step_order": 14,
                "step_id": "edit_review_decisions",
                "display_name": "Review Session Events",
                "lane": "human_review",
                "status": "complete",
                "started_at": None,
                "completed_at": None,
                "summary_comment": "Review was edited.",
                "inputs": ["knowledge/Faban/reviews/session20_review.yaml"],
                "outputs": ["knowledge/Faban/reviews/session20_review.yaml"],
                "dependencies": ["initialize_review"],
                "gate": "human_required",
                "rerun_policy": "edit_until_reviewed",
                "canon_impact": "review_record",
                "command": "web_review /sessions/sessionXX/review",
                "status_rules": {},
                "metadata": {},
                "links": [{"label": "Review Events", "url": "/sessions/session20/review"}],
                "issues": [],
            }, {
                "step_order": 18,
                "step_id": "update_lore_sections",
                "display_name": "Update Cross-Session Lore Sections",
                "lane": "canonization",
                "status": "complete",
                "started_at": None,
                "completed_at": None,
                "summary_comment": "Registries checked.",
                "inputs": ["knowledge/Faban/final/session20_summary.md"],
                "outputs": ["database lore rows"],
                "dependencies": ["write_final_summary"],
                "gate": "human_required",
                "rerun_policy": "canon_affecting_requires_confirmation",
                "canon_impact": "canon_file_or_database_canon",
                "command": "web_review lore and registry pages",
                "status_rules": {},
                "metadata": {},
                "links": [
                    {"label": "Lore Items", "url": "/lore-items"},
                    {"label": "NPCs", "url": "/npcs"},
                    {"label": "Locations", "url": "/locations"},
                    {"label": "Artifacts", "url": "/artifacts"},
                ],
                "issues": [],
            }],
        }

    def test_workflow_page_renders_ledger_without_detail_by_default(self):
        with patch("web_review.services.workflow.workflow_rows", return_value=self.workflow_rows()), \
             patch("web_review.services.workflow.workflow_detail") as detail:
            client = TestClient(app)
            response = client.get("/workflow")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Workflow Status", response.text)
        self.assertIn("/static/workflow-status-icon.png", response.text)
        self.assertIn("Session Workflow Ledger", response.text)
        self.assertIn("Session 20", response.text)
        self.assertIn('href="/workflow?session=20"', response.text)
        self.assertNotIn("workflow-detail-modal", response.text)
        detail.assert_not_called()

    def test_workflow_page_renders_detail_modal_when_session_selected(self):
        with patch("web_review.services.workflow.workflow_rows", return_value=self.workflow_rows()), \
             patch("web_review.services.workflow.workflow_detail", return_value=self.workflow_detail()):
            client = TestClient(app)
            response = client.get("/workflow?session=20")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Workflow Status", response.text)
        self.assertIn("Session Workflow Ledger", response.text)
        self.assertIn('role="dialog"', response.text)
        self.assertIn('aria-modal="true"', response.text)
        self.assertIn('href="/workflow" aria-label="Close workflow detail"', response.text)
        self.assertIn("Session 20", response.text)
        self.assertIn("Source Audio Registered", response.text)
        self.assertIn("Review Session Events", response.text)
        self.assertIn("Started", response.text)
        self.assertIn("Completed", response.text)
        self.assertIn("Comment", response.text)
        self.assertIn("Inputs", response.text)
        self.assertIn("Outputs", response.text)
        self.assertIn("2026-05-17 19:43:00", response.text)
        self.assertIn("2026-05-17 19:44:00", response.text)
        self.assertIn("audio/session20.wav", response.text)
        self.assertIn("not completed", response.text)
        self.assertIn("Needs Attention", response.text)
        self.assertIn("Missing output artifact knowledge/Faban/raw/session21_transcript.txt.", response.text)
        self.assertIn("Historical timestamps are estimated", response.text)
        self.assertIn("requires human action or review", response.text)
        self.assertIn("Source Audio Registered", response.text)
        self.assertIn("Review Session Events", response.text)
        self.assertIn('workflow-title-human-marker', response.text)
        self.assertIn('href="/workflow?session=20"', response.text)
        self.assertIn('href="/sessions/session20/review"', response.text)
        self.assertIn('href="/lore-items"', response.text)
        self.assertNotIn('href="/wells"', response.text)
        self.assertIn('href="/npcs"', response.text)
        self.assertIn('href="/locations"', response.text)
        self.assertIn('href="/artifacts"', response.text)
        self.assertIn("Protected Rerun", response.text)
        self.assertIn("Re-run Draft Extraction", response.text)

    def test_workflow_page_shows_blocked_draft_rerun_reasons(self):
        detail = self.workflow_detail()
        detail["can_rerun_draft"] = False
        detail["draft_rerun_guard"] = {
            "allowed": False,
            "reasons": ["Entity reviews already applied: session20_npcs_reviewed.json"],
        }
        with patch("web_review.services.workflow.workflow_rows", return_value=self.workflow_rows()), \
             patch("web_review.services.workflow.workflow_detail", return_value=detail):
            client = TestClient(app)
            response = client.get("/workflow?session=20&draft_rerun_blocked=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Draft extraction rerun was blocked", response.text)
        self.assertIn("Entity reviews already applied", response.text)
        self.assertNotIn("Re-run Draft Extraction</button>", response.text)

    def test_workflow_rerun_draft_route_queues_guarded_job(self):
        with patch("web_review.services.workflow.enqueue_draft_rerun") as enqueue:
            client = TestClient(app)
            response = client.post("/workflow/sessions/session21/rerun-draft", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/workflow?session=21&draft_rerun_queued=1")
        enqueue.assert_called_once_with(21)

    def test_workflow_rerun_draft_route_reports_blocked_guard(self):
        with patch("web_review.services.workflow.enqueue_draft_rerun", side_effect=workflow.WorkflowWriteError("blocked")):
            client = TestClient(app)
            response = client.post("/workflow/sessions/session21/rerun-draft", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/workflow?session=21&draft_rerun_blocked=1")

    def test_archive_mode_hides_workflow_from_navigation_and_route(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.reviews.dashboard_rows", return_value=[]):
            client = TestClient(app)
            dashboard_response = client.get("/")
            workflow_response = client.get("/workflow")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("Published Archive", dashboard_response.text)
        self.assertIn("World Map", dashboard_response.text)
        self.assertIn("/world-map/image", dashboard_response.text)
        self.assertNotIn("Workflow Status", dashboard_response.text)
        self.assertNotIn("Validation Queue", dashboard_response.text)
        self.assertNotIn('href="/workflow"', dashboard_response.text)
        self.assertEqual(workflow_response.status_code, 404)

    def test_workflow_api_returns_rows(self):
        with patch("web_review.services.workflow.workflow_rows", return_value=self.workflow_rows()):
            client = TestClient(app)
            response = client.get("/api/workflow")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["session_number"], 20)

    def test_archive_mode_blocks_workflow_api(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.workflow.workflow_rows") as rows:
            client = TestClient(app)
            response = client.get("/api/workflow")

        self.assertEqual(response.status_code, 404)
        rows.assert_not_called()

    def test_workflow_session_api_returns_detail(self):
        with patch("web_review.services.workflow.workflow_detail", return_value=self.workflow_detail()):
            client = TestClient(app)
            response = client.get("/api/workflow/sessions/session20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["steps"][0]["step_id"], "source_audio_registered")


class CommandServiceTest(unittest.TestCase):
    def test_apply_review_runs_existing_dm_query_command(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": "applied",
            "stderr": "",
        })()
        with patch("web_review.services.commands.subprocess.run", return_value=completed) as run:
            result = commands.apply_review(20)

        self.assertTrue(result.ok)
        command = run.call_args.args[0]
        self.assertEqual(command[-3:], [
            str(reviews.REPO_ROOT / "scripts" / "dm_query.py"),
            "apply-review",
            "session20",
        ])

    def test_write_final_summary_runs_existing_dm_query_command(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": "wrote final",
            "stderr": "",
        })()
        with patch("web_review.services.commands.subprocess.run", return_value=completed) as run:
            result = commands.write_final_summary(20)

        self.assertTrue(result.ok)
        command = run.call_args.args[0]
        self.assertEqual(command[-3:], [
            str(reviews.REPO_ROOT / "scripts" / "dm_query.py"),
            "write-final-summary",
            "session20",
        ])

    def test_refresh_event_drafts_runs_rag_refresh_events_command(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": "refreshed",
            "stderr": "",
        })()
        with patch("web_review.services.commands.subprocess.run", return_value=completed) as run:
            result = commands.refresh_event_drafts(20)

        self.assertTrue(result.ok)
        command = run.call_args.args[0]
        self.assertEqual(command[-3:], [
            str(reviews.REPO_ROOT / "scripts" / "rag.py"),
            "refresh-events",
            "session20",
        ])

    def test_run_health_runs_existing_dm_query_command(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": "healthy",
            "stderr": "",
        })()
        with patch("web_review.services.commands.subprocess.run", return_value=completed) as run:
            result = commands.run_health()

        self.assertTrue(result.ok)
        command = run.call_args.args[0]
        self.assertEqual(command[-2:], [
            str(reviews.REPO_ROOT / "scripts" / "dm_query.py"),
            "health",
        ])

    def test_run_health_includes_session_review_readiness_errors(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": "healthy",
            "stderr": "",
        })()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(reviews, "REVIEWS_DIR", Path(tmp)), \
             patch("web_review.services.commands.subprocess.run", return_value=completed):
            (Path(tmp) / "session01_review.yaml").write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [
                    {"id": "event-003", "sequence": 3, "decision": "corrected", "canonical_text": "Chest appears.", "event_type": "lore", "significance": 3, "reason": ""},
                ],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")
            result = commands.run_health(session_number=1)

        self.assertFalse(result.ok)
        self.assertIn("healthy", result.stdout)
        self.assertIn("Review Readiness", result.stderr)
        self.assertIn("Order 3 event event-003 is corrected but missing reason.", result.stderr)

    def test_run_smoke_test_reports_multiline_category_summary(self):
        response = type("Response", (), {
            "status": 200,
            "read": lambda self: b"Session Review Ledger Campaign Timeline Open Threads Lore Items session_count [",
            "__enter__": lambda self: self,
            "__exit__": lambda self, exc_type, exc, traceback: False,
        })()
        with patch("web_review.services.commands.urllib.request.urlopen", return_value=response), \
             patch("web_review.services.commands.db.fetch_all", return_value=[{"session_count": 21}]):
            result = commands.run_smoke_test()

        self.assertTrue(result.ok)
        self.assertIn("Tests run: 7", result.stdout)
        self.assertIn("Passed: 7", result.stdout)
        self.assertIn("Failed: 0", result.stdout)
        self.assertIn("Categories: API, Database, Routes", result.stdout)
        self.assertIn("- Routes", result.stdout)
        self.assertIn("PASS /timeline: ok", result.stdout)
        self.assertIn("PASS session count query: 21 sessions", result.stdout)

    def test_run_static_export_runs_export_script(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": "exported",
            "stderr": "",
        })()
        with patch("web_review.services.commands.subprocess.run", return_value=completed) as run:
            result = commands.run_static_export("http://archive:8000")

        self.assertTrue(result.ok)
        command = run.call_args.args[0]
        self.assertIn(str(reviews.REPO_ROOT / "scripts" / "export_static_archive.py"), command)
        self.assertIn("http://archive:8000", command)
        self.assertIn(str(reviews.REPO_ROOT / "dist" / "archive"), command)

    def test_publish_static_archive_runs_publish_script(self):
        completed = type("Completed", (), {
            "returncode": 0,
            "stdout": "published",
            "stderr": "",
        })()
        with patch("web_review.services.commands.subprocess.run", return_value=completed) as run:
            result = commands.publish_static_archive("http://archive:8000", "/tmp/static-repo", push=True)

        self.assertTrue(result.ok)
        command = run.call_args.args[0]
        self.assertIn(str(reviews.REPO_ROOT / "scripts" / "publish_static_archive.py"), command)
        self.assertIn("http://archive:8000", command)
        self.assertIn("/tmp/static-repo", command)
        self.assertIn("--push", command)


class StaticArchiveExportTest(unittest.TestCase):
    def test_rewrite_html_maps_dynamic_archive_links_to_static_paths(self):
        html = (
            '<form method="post" action="/sessions/session21/review/save">'
            '<link rel="stylesheet" href="http://web_archive:8000/static/review.css">'
            '<a href="/sessions/session21/review">Open</a>'
            '<a href="/sessions/session21/review?source=diary">Diary</a>'
            '<a href="/sessions/session21/review?source=final">Summary</a>'
            '<a href="/songbook/3/lyrics">Lyrics</a>'
            '<audio src="/songbook/3/audio"></audio>'
            '</form>'
        )

        rewritten = export_static_archive.rewrite_html(html)

        self.assertIn('method="get" action="#"', rewritten)
        self.assertIn('href="/static/review.css"', rewritten)
        self.assertIn('href="/sessions/session21/summary/"', rewritten)
        self.assertIn('href="/sessions/session21/diary/"', rewritten)
        self.assertIn('href="/songbook/3/lyrics/"', rewritten)
        self.assertIn('src="/media/songbook/03/song.mp3"', rewritten)

    def test_discover_session_keys_from_dashboard_links(self):
        html = '<a href="/sessions/session02/review">Open</a><a href="/sessions/session21/review">Open</a>'
        self.assertEqual(export_static_archive.discover_session_keys(html), ["session02", "session21"])

    def test_resolve_repo_media_path_maps_legacy_songbook_path_to_campaign_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            migrated = root / "campaigns" / "farrlind" / "songbook" / "Song" / "song.mp3"
            migrated.parent.mkdir(parents=True)
            migrated.write_bytes(b"mp3")

            with patch.object(export_static_archive, "REPO_ROOT", root), \
                 patch("raglib.campaign.REPO_ROOT", root):
                resolved = export_static_archive.resolve_repo_media_path("knowledge/Faban/songbook/Song/song.mp3")

        self.assertEqual(resolved, migrated)

    def test_publish_archive_sets_repo_local_git_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)

            publish_static_archive.ensure_git_identity(repo)

            name = subprocess.run(["git", "config", "--get", "user.name"], cwd=repo, check=True, capture_output=True, text=True)
            email = subprocess.run(["git", "config", "--get", "user.email"], cwd=repo, check=True, capture_output=True, text=True)

        self.assertEqual(name.stdout.strip(), "Kurt Gustafson")
        self.assertEqual(email.stdout.strip(), "kgustafson2@gmail.com")

    def test_apply_review_route_requires_reviewed_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/apply", data={
                    "source": "diary",
                    "view": "raw",
                })

        self.assertEqual(response.status_code, 409)

    def test_apply_review_route_runs_command_for_reviewed_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "reviewed",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.commands.apply_review", return_value=commands.CommandResult(0, "ok", "")) as apply, \
                 patch("web_review.services.workflow.sync_session_workflow") as sync:
                client = TestClient(app)
                response = client.post("/sessions/session01/review/apply", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("applied=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        apply.assert_called_once_with(1)
        sync.assert_called_once_with(1)

    def test_apply_review_route_reports_command_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "reviewed",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.commands.apply_review", return_value=commands.CommandResult(1, "", "boom")):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/apply", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("apply_failed=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])

    def test_write_final_summary_route_requires_applied_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "reviewed",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/write-final-summary", data={
                    "source": "final",
                    "view": "print",
                })

        self.assertEqual(response.status_code, 409)

    def test_write_final_summary_route_runs_command_for_applied_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "applied",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.commands.write_final_summary", return_value=commands.CommandResult(0, "ok", "")) as write, \
                 patch("web_review.services.workflow.sync_session_workflow") as sync:
                client = TestClient(app)
                response = client.post("/sessions/session01/review/write-final-summary", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("final_written=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        write.assert_called_once_with(1)
        sync.assert_called_once_with(1)

    def test_write_final_summary_route_reports_command_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "applied",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.commands.write_final_summary", return_value=commands.CommandResult(1, "", "boom")):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/write-final-summary", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("final_failed=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])

    def test_run_health_route_runs_command_and_reports_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "in_review",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.commands.run_health", return_value=commands.CommandResult(0, "healthy", "")) as health:
                client = TestClient(app)
                response = client.post("/sessions/session01/review/health", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("health_ok=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        health.assert_called_once_with(session_number=1)

    def test_run_health_route_reports_command_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reviews_dir = root / "reviews"
            clean = root / "clean"
            final = root / "final"
            clean.mkdir()
            final.mkdir()
            path = reviews_dir / "session01_review.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump({
                "session": "session01",
                "status": "applied",
                "items": [],
                "added_items": [],
            }, sort_keys=False), encoding="utf-8")

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final), \
                 patch("web_review.services.commands.run_health", return_value=commands.CommandResult(1, "", "needs attention")):
                client = TestClient(app)
                response = client.post("/sessions/session01/review/health", data={
                    "source": "diary",
                    "view": "raw",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("health_failed=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])


if __name__ == "__main__":
    unittest.main()
