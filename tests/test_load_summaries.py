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


if __name__ == "__main__":
    unittest.main()
