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

    def test_review_events_for_session_uses_source_text_for_added_item_without_canonical_text(self):
        review = {
            "session": "session19",
            "status": "applied",
            "items": [
                {
                    "id": "event-011",
                    "decision": "added",
                    "source_text": 'Faban wrote "The Battle of Balrog Square."',
                    "canonical_text": "",
                    "event_type": "acquisition",
                    "location": "Balrog",
                    "significance": 4,
                }
            ],
        }

        events = load_summaries.review_events_for_session({"session_number": 19}, review)

        self.assertEqual(events[0]["description"], 'Faban wrote "The Battle of Balrog Square."')
        self.assertEqual(events[0]["event_type"], "acquisition")

    def test_review_events_for_session_orders_by_optional_sequence(self):
        review = {
            "session": "session17",
            "status": "applied",
            "items": [
                {"id": "event-001", "sequence": 2, "decision": "accepted", "source_text": "Second event"},
                {"id": "event-002", "sequence": 4, "decision": "accepted", "source_text": "Fourth event"},
            ],
            "added_items": [
                {"id": "added-001", "sequence": 1, "decision": "added", "canonical_text": "First event"},
                {"id": "added-002", "sequence": 3.5, "decision": "added", "canonical_text": "Between events"},
            ],
        }

        events = load_summaries.review_events_for_session({"session_number": 17}, review)

        self.assertEqual([event["description"] for event in events], [
            "First event",
            "Second event",
            "Between events",
            "Fourth event",
        ])

    def test_review_events_for_session_ignores_in_review_documents(self):
        self.assertIsNone(load_summaries.review_events_for_session({}, {"status": "in_review"}))

    def test_review_primary_locations_uses_completed_review_location(self):
        reviews = {
            18: {"status": "applied", "primary_location": "Balrog"},
            17: {"status": "in_review", "primary_location": "Paramon"},
            16: {"status": "applied", "primary_location": ""},
        }

        self.assertEqual(load_summaries.review_primary_locations(reviews), {18: "Balrog"})

    def test_review_location_names_collects_completed_review_locations(self):
        reviews = {
            17: {
                "status": "reviewed",
                "primary_location": "Paramon",
                "items": [
                    {"decision": "accepted", "location": "Crossroads"},
                    {"decision": "rejected", "location": "Ignored"},
                ],
                "added_items": [
                    {"decision": "added", "location": "Balrog"},
                ],
            },
            16: {
                "status": "in_review",
                "primary_location": "Draft Place",
                "items": [{"decision": "accepted", "location": "Draft Event Place"}],
            },
        }

        self.assertEqual(load_summaries.review_location_names(reviews), {"Paramon", "Crossroads", "Balrog"})

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

    def test_build_sql_uses_review_primary_location(self):
        summaries = [
            {
                "session_number": 18,
                "physical_date": "2026-02-22",
                "in_game_date": "1832 AS Namal 18",
                "title": "The Falling and the Forge",
                "summary": "The party met Saiffi.",
                "events": ["The party met Saiffi"],
                "source_path": "session18_summary.md",
                "location": "",
            }
        ]
        reviews = {
            18: {
                "session": "session18",
                "status": "applied",
                "primary_location": "Balrog",
                "items": [],
                "added_items": [],
            }
        }

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value=reviews):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("(SELECT id FROM location WHERE name = 'Balrog' LIMIT 1)", sql)

    def test_build_sql_inserts_review_introduced_locations(self):
        summaries = [
            {
                "session_number": 17,
                "physical_date": "2026-02-07",
                "in_game_date": "1832 AS Namal 18",
                "title": "After Iron Paw",
                "summary": "The party visited a fair.",
                "events": ["The party visited a fair."],
                "source_path": "session17_summary.md",
                "location": "Paramon",
            }
        ]
        reviews = {
            17: {
                "session": "session17",
                "status": "reviewed",
                "primary_location": "Paramon",
                "items": [
                    {
                        "id": "event-001",
                        "decision": "accepted",
                        "source_text": "The party visited a fair.",
                        "event_type": "social",
                        "location": "Crossroads",
                        "significance": 4,
                    }
                ],
            }
        }

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value=reviews):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Crossroads'", sql)
        self.assertIn("Location introduced through session review.", sql)
        self.assertIn("(SELECT id FROM location WHERE name = 'Crossroads' LIMIT 1)", sql)

    def test_canon_npc_sql_updates_then_inserts_without_unique_constraint(self):
        npc = {
            "name": "Alistair",
            "first_seen_session": 20,
            "location": "Coast near Catur",
            "description": "Coastal boat contact.",
            "status": "alive",
        }

        sql = load_summaries.canon_npc_sql(npc)

        self.assertIn("UPDATE npc", sql)
        self.assertIn("INSERT INTO npc", sql)
        self.assertIn("WHERE NOT EXISTS (SELECT 1 FROM npc WHERE name = 'Alistair')", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 20", sql)
        self.assertIn("(SELECT id FROM location WHERE name = 'Coast near Catur' LIMIT 1)", sql)
        self.assertNotIn("ON CONFLICT (name)", sql)

    def test_build_sql_scrubs_reviewed_canon_npcs(self):
        summaries = [
            {
                "session_number": 20,
                "physical_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "summary": "Alistair gave the party a boat.",
                "events": ["Alistair gave the party a boat."],
                "source_path": "session20_summary.md",
                "location": "Coast near Catur",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("Loaded from reviewed canon NPC scrub.", sql)
        self.assertIn("Alistair", sql)
        self.assertIn("Coastal boat contact who gave the party a boat near Catur.", sql)

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
