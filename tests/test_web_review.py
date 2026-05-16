import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from web_review.services import canon, commands, lore, reviews, workflow
from web_review.app import BACKUP_DOWNLOADS, COMMAND_RESULTS, app, app_version
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

    def test_session_workspace_loads_selected_source_and_sorts_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            final = root / "final"
            reviews_dir = root / "reviews"
            clean.mkdir()
            final.mkdir()
            (clean / "session03_diary.md").write_text("diary text", encoding="utf-8")
            (clean / "session03_summary.md").write_text("draft text", encoding="utf-8")
            (final / "session03_summary.md").write_text("final text", encoding="utf-8")
            self.write_review(root, "session03", {
                "session": "session03",
                "status": "applied",
                "session_title": "Fey Woods",
                "items": [
                    {"id": "event-002", "sequence": 2, "decision": "accepted", "applied_status": "applied"},
                    {"id": "event-001", "sequence": 1, "decision": "accepted", "applied_status": "applied"},
                ],
                "added_items": [
                    {"id": "added-001", "sequence": 1.5, "decision": "added", "canonical_text": "Added", "event_type": "social", "location": "Fey Woods", "significance": 3, "reason": "Important", "applied_status": "applied"},
                ],
            })

            with patch.object(reviews, "REVIEWS_DIR", reviews_dir), \
                 patch.object(reviews, "CLEAN_DIR", clean), \
                 patch.object(reviews, "FINAL_DIR", final):
                workspace = reviews.session_workspace(3, source="final")

        self.assertEqual(workspace["source_label"], "Final Summary")
        self.assertEqual(workspace["source_text"], "final text")
        self.assertEqual(workspace["source_view"], "raw")
        self.assertTrue(workspace["review_locked"])
        self.assertEqual([item["id"] for item in workspace["items"]], ["event-001", "added-001", "event-002"])
        self.assertEqual(workspace["validation"], ["No review validation issues found."])

    def test_wells_lore_write_creates_parent_and_trims_trailing_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lore" / "wells_of_magic.md"
            lore.write_wells_of_magic("The Wells remember.\n\n", path=path)

            self.assertEqual(path.read_text(encoding="utf-8"), "The Wells remember.\n")

    def test_validate_review_document_reports_required_corrected_fields(self):
        notes = reviews.validate_review_document({
            "status": "reviewed",
            "items": [
                {"id": "event-001", "sequence": 1, "decision": "corrected", "canonical_text": ""},
            ],
        })

        self.assertIn("event-001 is corrected but missing canonical_text.", notes)
        self.assertIn("event-001 is corrected but missing location.", notes)

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
                {"id": "event-001", "sequence": 1, "decision": "accepted"},
            ],
            "added_items": [],
        }
        updated, errors = reviews.mark_reviewed_document(document, reviewed_on="2026-05-06")

        self.assertEqual(errors, [])
        self.assertEqual(updated["status"], "reviewed")
        self.assertEqual(updated["reviewed_on"], "2026-05-06")


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

    def test_print_view_renders_source_markdown(self):
        client = TestClient(app)
        response = client.get("/sessions/session20/review?source=final&view=print")

        self.assertEqual(response.status_code, 200)
        self.assertIn("source-rendered", response.text)
        self.assertIn("Source</a>", response.text)
        self.assertIn("Print</a>", response.text)

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

    def test_save_review_route_requires_confirmation_for_unknown_location(self):
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
            self.assertIn("location_confirm_failed=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["location"], "Bentrios")

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
                 patch.object(reviews, "FINAL_DIR", final):
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

    def test_add_item_route_requires_confirmation_for_unknown_location(self):
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
            self.assertIn("location_confirm_failed=1", response.headers["location"])
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["added_items"], [])

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
            "enemy_outcome": "defeated",
            "enemy_confidence": "high",
            "enemy_notes": "",
        }]
        with patch("web_review.db.fetch_all", return_value=db_rows):
            rows = canon.combat_encounter_rows()

        self.assertEqual(rows[0]["session_span"], "Session 00 -> Session 01")

    def test_murder_hobo_count_sums_known_killed_and_defeated_enemies(self):
        summary = canon.murder_hobo_count([
            {
                "enemies": [
                    {"quantity": 1, "outcome": "defeated"},
                    {"quantity": 2, "outcome": "killed"},
                    {"quantity": 5, "outcome": "fled"},
                    {"quantity": None, "outcome": "killed"},
                    {"quantity": 3, "outcome": "defeated_or_fled"},
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
                "song_number": 1,
                "title": "Test Song",
                "style": "ballad",
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

    def test_locations_add_modal_renders_form(self):
        with patch("web_review.services.canon.location_rows", return_value=self.location_rows()), \
             patch("web_review.services.canon.location_types", return_value=[{"id": 1, "type_name": "city"}]):
            client = TestClient(app)
            response = client.get("/locations?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Location", response.text)
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
        self.assertNotIn('role="dialog"', response.text)

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
        self.assertNotIn('role="dialog"', response.text)

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
        self.assertIn("Add New", response.text)
        self.assertNotIn("Add Artifact</h2>", response.text)

    def test_artifacts_add_modal_renders_form(self):
        with patch("web_review.services.canon.artifact_rows", return_value=self.artifact_rows()), \
             patch("web_review.services.canon.artifact_types", return_value=self.artifact_types()):
            client = TestClient(app)
            response = client.get("/artifacts?modal=add")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Add Artifact", response.text)
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
        self.assertNotIn('role="dialog"', response.text)

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
        self.assertIn('href="/open-threads/1/edit"', response.text)
        self.assertIn('action="/open-threads/1/delete"', response.text)
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
        self.assertNotIn("Edit</a>", response.text)
        self.assertNotIn("Delete</button>", response.text)
        self.assertNotIn('role="dialog"', response.text)

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
                    "outcome": "defeated",
                    "confidence": "high",
                    "notes": "Dragon defeated.",
                },
                {
                    "name": "Cultist spellcaster",
                    "enemy_type": "cultist_spellcaster",
                    "quantity": 2,
                    "outcome": "killed",
                    "confidence": "high",
                    "notes": "Both killed.",
                },
                {
                    "name": "Cultist melee fighter",
                    "enemy_type": "cultist_melee",
                    "quantity": 3,
                    "outcome": "killed",
                    "confidence": "high",
                    "notes": "All killed.",
                },
            ],
        }]

    def test_combat_encounters_page_renders_ledger_and_murder_hobo_count(self):
        with patch("web_review.services.canon.combat_encounter_rows", return_value=self.combat_rows()):
            client = TestClient(app)
            response = client.get("/combat-encounters")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Combat Encounters", response.text)
        self.assertIn("Orsydon summoned in Balrog", response.text)
        self.assertIn("Murder Hobo Count", response.text)
        self.assertIn(">6<", response.text)
        self.assertIn('href="/combat-encounters"', response.text)

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
                    "title": "Salt, Steel, and the Distance Between Legends",
                    "summary": "",
                    "primary_location": "Coast near Catur",
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
        self.assertIn("campaign-flow", response.text)
        self.assertIn('class="session-orb"', response.text)
        self.assertIn('href="#session-20-modal"', response.text)
        self.assertIn('title="Session 20: Salt, Steel, and the Distance Between Legends"', response.text)
        self.assertIn('data-tooltip="Session 20: Salt, Steel, and the Distance Between Legends"', response.text)
        self.assertIn('id="session-20-modal"', response.text)
        self.assertIn('role="dialog"', response.text)
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
        client = TestClient(app)
        response = client.get("/project-utilities")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Project Utilities", response.text)
        self.assertIn("View Todo", response.text)
        self.assertIn("Backup Database", response.text)
        self.assertIn("Run Smoke Test", response.text)
        self.assertIn("todo.md", response.text)
        self.assertIn('href="/project-utilities"', response.text)

    def test_project_utilities_page_renders_revision_viewer(self):
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


class SongbookRouteTest(unittest.TestCase):
    def song_rows(self):
        return [{
            "song_number": 1,
            "title": "The Off-Key Dragon",
            "style": "tavern_song",
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
        self.assertIn("Read Faban", response.text)
        self.assertIn("A bard", response.text)

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


class WellsLoreRouteTest(unittest.TestCase):
    def test_wells_page_renders_single_lore_editor(self):
        with patch("web_review.services.lore.read_wells_of_magic", return_value="Six Wells Exist"):
            client = TestClient(app)
            response = client.get("/wells")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Wells of Magic", response.text)
        self.assertIn("Six Wells Exist", response.text)
        self.assertIn('name="lore_text"', response.text)
        self.assertIn('rows="20"', response.text)
        self.assertIn('href="/wells"', response.text)

    def test_archive_mode_renders_wells_as_read_only_lore(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.lore.read_wells_of_magic", return_value="## Six Wells\n\nThey never lie."):
            client = TestClient(app)
            response = client.get("/wells")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<h2>Six Wells</h2>", response.text)
        self.assertNotIn('name="lore_text"', response.text)
        self.assertNotIn("Save Lore", response.text)

    def test_save_wells_lore_writes_text(self):
        with patch("web_review.services.lore.write_wells_of_magic") as write_lore:
            client = TestClient(app)
            response = client.post("/wells", data={
                "lore_text": "The Wells never lie.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("saved=1", response.headers["location"])
        write_lore.assert_called_once_with("The Wells never lie.")


class WorkflowServiceTest(unittest.TestCase):
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
        self.assertIn("workflow_run", fetch.call_args.args[0])
        self.assertIn("workflow_step_state", fetch.call_args.args[0])

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
            "inputs": ["audio/session20.wav"],
            "outputs": ["audio/session20.wav"],
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
        self.assertEqual(loaded["attention_items"], [])

    def test_step_issues_surface_status_and_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "knowledge" / "Faban" / "clean").mkdir(parents=True)
            (root / "knowledge" / "Faban" / "clean" / "session21_diary.md").write_text("diary", encoding="utf-8")
            with patch("web_review.services.reviews.REPO_ROOT", root):
                issues = workflow.step_issues({
                    "status": "pending",
                    "summary_comment": "Waiting for transcript.",
                    "inputs": [
                        "knowledge/Faban/clean/session21_diary.md",
                        "knowledge/Faban/raw/session21_transcript.txt",
                    ],
                    "outputs": ["knowledge/Faban/clean/session21_summary.md"],
                })

        self.assertIn("Waiting for transcript.", issues)
        self.assertIn("Missing input artifact knowledge/Faban/raw/session21_transcript.txt.", issues)
        self.assertIn("Missing output artifact knowledge/Faban/clean/session21_summary.md.", issues)

    def test_step_issues_ignore_optional_corrections_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("web_review.services.reviews.REPO_ROOT", Path(tmp)):
                issues = workflow.step_issues({
                    "status": "complete",
                    "summary_comment": "",
                    "inputs": ["knowledge/Faban/notes/session20_corrections.md"],
                    "outputs": [],
                })

        self.assertEqual(issues, [])

    def test_step_links_route_review_and_registry_steps(self):
        self.assertEqual(
            workflow.step_links("edit_review_decisions", 20),
            [{"label": "Review", "url": "/sessions/session20/review"}],
        )
        self.assertEqual(
            workflow.step_links("write_final_summary", 20),
            [{"label": "Final Summary", "url": "/sessions/session20/review?source=final&view=print"}],
        )
        self.assertEqual(
            workflow.step_links("update_lore_sections", 20),
            [
                {"label": "Wells", "url": "/wells"},
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
            "steps": [{
                "step_order": 1,
                "step_id": "source_audio_registered",
                "display_name": "Source Audio Registered",
                "lane": "intake",
                "status": "complete",
                "started_at": None,
                "completed_at": None,
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
                "display_name": "Edit Review Decisions",
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
                "command": "web_review session review page",
                "status_rules": {},
                "metadata": {},
                "links": [{"label": "Review", "url": "/sessions/session20/review"}],
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
                "outputs": ["knowledge/Faban/lore/wells_of_magic.md"],
                "dependencies": ["write_final_summary"],
                "gate": "human_required",
                "rerun_policy": "canon_affecting_requires_confirmation",
                "canon_impact": "canon_file_or_database_canon",
                "command": "web_review lore and registry pages",
                "status_rules": {},
                "metadata": {},
                "links": [
                    {"label": "Wells", "url": "/wells"},
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
        self.assertIn("Session Workflow Ledger", response.text)
        self.assertIn("Session 20", response.text)
        self.assertIn('href="/workflow?session=20"', response.text)
        self.assertNotIn('role="dialog"', response.text)
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
        self.assertIn("Edit Review Decisions", response.text)
        self.assertIn("Needs Attention", response.text)
        self.assertIn("Missing output artifact knowledge/Faban/raw/session21_transcript.txt.", response.text)
        self.assertIn("Historical timestamps are estimated", response.text)
        self.assertIn('href="/workflow?session=20"', response.text)
        self.assertIn('href="/sessions/session20/review"', response.text)
        self.assertIn('href="/wells"', response.text)
        self.assertIn('href="/npcs"', response.text)
        self.assertIn('href="/locations"', response.text)
        self.assertIn('href="/artifacts"', response.text)

    def test_archive_mode_hides_workflow_from_navigation_and_route(self):
        with patch.dict("os.environ", {"FARRLIND_INTERFACE_MODE": "archive"}), \
             patch("web_review.services.reviews.dashboard_rows", return_value=[]):
            client = TestClient(app)
            dashboard_response = client.get("/")
            workflow_response = client.get("/workflow")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("Published Archive", dashboard_response.text)
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

    def test_run_smoke_test_reports_multiline_category_summary(self):
        response = type("Response", (), {
            "status": 200,
            "read": lambda self: b"Session Review Ledger Campaign Timeline Open Threads session_count",
            "__enter__": lambda self: self,
            "__exit__": lambda self, exc_type, exc, traceback: False,
        })()
        with patch("web_review.services.commands.urllib.request.urlopen", return_value=response), \
             patch("web_review.services.commands.db.fetch_all", return_value=[{"session_count": 21}]):
            result = commands.run_smoke_test()

        self.assertTrue(result.ok)
        self.assertIn("Tests run: 5", result.stdout)
        self.assertIn("Passed: 5", result.stdout)
        self.assertIn("Failed: 0", result.stdout)
        self.assertIn("Categories: API, Database, Routes", result.stdout)
        self.assertIn("- Routes", result.stdout)
        self.assertIn("PASS /timeline: ok", result.stdout)
        self.assertIn("PASS session count query: 21 sessions", result.stdout)

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
                 patch("web_review.services.commands.apply_review", return_value=commands.CommandResult(0, "ok", "")) as apply:
                client = TestClient(app)
                response = client.post("/sessions/session01/review/apply", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("applied=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        apply.assert_called_once_with(1)

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
                 patch("web_review.services.commands.write_final_summary", return_value=commands.CommandResult(0, "ok", "")) as write:
                client = TestClient(app)
                response = client.post("/sessions/session01/review/write-final-summary", data={
                    "source": "final",
                    "view": "print",
                }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("final_written=1", response.headers["location"])
        self.assertIn("command_result=", response.headers["location"])
        write.assert_called_once_with(1)

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
        health.assert_called_once_with()

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
