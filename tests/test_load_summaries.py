import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "load_summaries.py"

spec = importlib.util.spec_from_file_location("load_summaries", MODULE_PATH)
load_summaries = importlib.util.module_from_spec(spec)
sys.modules["load_summaries"] = load_summaries
spec.loader.exec_module(load_summaries)


class LoadSummariesTest(unittest.TestCase):
    def test_canon_decision_helpers_group_session_updates(self):
        decisions = {
            "session_primary_locations": [
                {
                    "session": "session20",
                    "canonical": "Coast near Catur",
                    "status": "needs_db_update",
                }
            ],
            "event_review_decisions": [
                {
                    "session": "session20",
                    "status": "needs_db_update",
                    "decision_type": "missing_primary_event",
                    "description": "Negotiated with fishermen for a vessel.",
                },
                {
                    "session": "session20",
                    "status": "rejected",
                    "decision_type": "missing_primary_event",
                    "description": "Should not load.",
                },
            ],
        }

        primary = load_summaries.canon_primary_locations(decisions)
        events = load_summaries.canon_event_decisions(decisions)

        self.assertEqual(primary[20]["canonical"], "Coast near Catur")
        self.assertEqual(len(events[20]), 1)
        self.assertIn("fishermen", events[20][0]["description"])

    def test_detect_location_uses_coast_alias_before_catur_city(self):
        self.assertEqual(load_summaries.detect_location("Arrived at Catur shoreline"), "Coast near Catur")
        self.assertEqual(load_summaries.detect_location("Preparing to enter Catur"), "Catur")

    def test_build_sql_applies_session20_canon_location_and_event(self):
        summaries = [
            {
                "session_number": 20,
                "physical_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "summary": "The party arrived near Catur.",
                "events": ["Arrived at Catur shoreline"],
                "source_path": "session20_summary.md",
                "location": "Balrog",
            }
        ]
        decisions = {
            "session_primary_locations": [
                {
                    "session": "session20",
                    "canonical": "Coast near Catur",
                    "status": "needs_db_update",
                }
            ],
            "event_review_decisions": [
                {
                    "session": "session20",
                    "status": "needs_db_update",
                    "decision_type": "missing_primary_event",
                    "event_type": "social",
                    "significance": 4,
                    "location": "Coast near Catur",
                    "description": "The party negotiated with fishermen for a vessel.",
                    "reason": "Key setup event.",
                }
            ],
        }

        with patch("load_summaries.load_canon_decisions", return_value=decisions):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                sql = load_summaries.build_sql(summaries)

        self.assertIn("INSERT INTO location (name, location_type_id, description)", sql)
        self.assertIn("'Coast near Catur'", sql)
        self.assertIn("The party negotiated with fishermen for a vessel.", sql)
        self.assertIn("Loaded from canon_decisions.yaml", sql)
        self.assertIn("(SELECT id FROM location WHERE name = 'Coast near Catur' LIMIT 1)", sql)

    def test_review_events_for_session_respects_review_decisions(self):
        summary = {
            "session_number": 20,
            "events": ["Draft event"],
        }
        review = {
            "session": "session20",
            "status": "reviewed",
            "items": [
                {
                    "id": "event-001",
                    "decision": "accepted",
                    "source_text": "Accepted event",
                    "event_type": "travel",
                    "location": "Coast near Catur",
                    "significance": 4,
                },
                {
                    "id": "event-002",
                    "decision": "corrected",
                    "source_text": "Wrong event",
                    "canonical_text": "Corrected event",
                    "event_type": "social",
                    "location": "Coast near Catur",
                    "significance": 5,
                },
                {
                    "id": "event-003",
                    "decision": "rejected",
                    "source_text": "Rejected event",
                },
                {
                    "id": "event-004",
                    "decision": "pending",
                    "source_text": "Pending event",
                },
            ],
            "added_items": [
                {
                    "id": "added-001",
                    "decision": "added",
                    "canonical_text": "Added event",
                    "event_type": "discovery",
                    "location": "Catur",
                    "significance": 4,
                }
            ],
        }

        events = load_summaries.review_events_for_session(summary, review)

        self.assertEqual([event["description"] for event in events], [
            "Accepted event",
            "Corrected event",
            "Added event",
        ])
        self.assertEqual(events[1]["event_type"], "social")
        self.assertIn("event-001", events[0]["notes"])

    def test_review_events_for_session_ignores_in_review_documents(self):
        self.assertIsNone(load_summaries.review_events_for_session({}, {"status": "in_review"}))

    def test_build_sql_uses_reviewed_events_instead_of_summary_events(self):
        summaries = [
            {
                "session_number": 20,
                "physical_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "summary": "The party arrived near Catur.",
                "events": ["Draft event to replace"],
                "source_path": "session20_summary.md",
                "location": "Coast near Catur",
            }
        ]
        reviews = {
            20: {
                "session": "session20",
                "status": "reviewed",
                "items": [
                    {
                        "id": "event-001",
                        "decision": "accepted",
                        "source_text": "Reviewed accepted event",
                        "event_type": "travel",
                        "location": "Coast near Catur",
                        "significance": 4,
                    }
                ],
                "added_items": [],
            }
        }

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value=reviews):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("Reviewed accepted event", sql)
        self.assertNotIn("Draft event to replace", sql)
        self.assertIn("Loaded from session20 review: event-001", sql)

    def test_build_sql_dedupes_canon_events_already_in_review(self):
        event_text = "The party negotiated with local fishermen for a vessel."
        summaries = [
            {
                "session_number": 20,
                "physical_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "summary": "The party arrived near Catur.",
                "events": ["Draft event to replace"],
                "source_path": "session20_summary.md",
                "location": "Coast near Catur",
            }
        ]
        reviews = {
            20: {
                "session": "session20",
                "status": "reviewed",
                "items": [
                    {
                        "id": "event-001",
                        "decision": "accepted",
                        "source_text": event_text,
                        "event_type": "social",
                        "location": "Coast near Catur",
                        "significance": 4,
                    }
                ],
                "added_items": [],
            }
        }
        decisions = {
            "event_review_decisions": [
                {
                    "session": "session20",
                    "decision_type": "missing_primary_event",
                    "status": "applied",
                    "description": event_text,
                    "event_type": "social",
                    "location": "Coast near Catur",
                    "significance": 4,
                }
            ]
        }

        with patch("load_summaries.load_canon_decisions", return_value=decisions):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value=reviews):
                    sql = load_summaries.build_sql(summaries)

        self.assertEqual(sql.count(event_text), 1)
        self.assertNotIn("Loaded from canon_decisions.yaml", sql)


if __name__ == "__main__":
    unittest.main()
