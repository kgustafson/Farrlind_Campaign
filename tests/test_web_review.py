import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from web_review.services import canon, commands, lore, reviews
from web_review.app import COMMAND_RESULTS, app, app_version
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


class WellsLoreRouteTest(unittest.TestCase):
    def test_wells_page_renders_single_lore_editor(self):
        with patch("web_review.services.lore.read_wells_of_magic", return_value="Six Wells Exist"):
            client = TestClient(app)
            response = client.get("/wells")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Wells of Magic", response.text)
        self.assertIn("Six Wells Exist", response.text)
        self.assertIn('name="lore_text"', response.text)
        self.assertIn('href="/wells"', response.text)

    def test_save_wells_lore_writes_text(self):
        with patch("web_review.services.lore.write_wells_of_magic") as write_lore:
            client = TestClient(app)
            response = client.post("/wells", data={
                "lore_text": "The Wells never lie.",
            }, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("saved=1", response.headers["location"])
        write_lore.assert_called_once_with("The Wells never lie.")


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
