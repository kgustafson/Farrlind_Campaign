import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from web_review.services import canon, reviews
from web_review.app import app
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
    def test_print_view_renders_source_markdown(self):
        client = TestClient(app)
        response = client.get("/sessions/session20/review?source=final&view=print")

        self.assertEqual(response.status_code, 200)
        self.assertIn("source-rendered", response.text)
        self.assertIn("Source</a>", response.text)
        self.assertIn("Print</a>", response.text)

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


class CanonServiceTest(unittest.TestCase):
    def test_locations_returns_ordered_names_from_db_rows(self):
        with patch("web_review.db.fetch_all", return_value=[{"name": "Balrog"}, {"name": "Catur"}]) as fetch:
            self.assertEqual(canon.locations(), ["Balrog", "Catur"])
        self.assertIn("FROM location", fetch.call_args.args[0])

    def test_event_types_returns_ordered_names_from_db_rows(self):
        with patch("web_review.db.fetch_all", return_value=[{"type_name": "combat"}, {"type_name": "social"}]):
            self.assertEqual(canon.event_types(), ["combat", "social"])


if __name__ == "__main__":
    unittest.main()
