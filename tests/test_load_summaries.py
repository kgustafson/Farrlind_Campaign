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

    def test_detect_location_distinguishes_fey_woods_from_thataways(self):
        self.assertEqual(load_summaries.detect_location("The party approaches the Fey Wilds"), "Fey Woods")
        self.assertEqual(load_summaries.detect_location("The party reaches Thataways"), "Thataways")

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

    def test_canon_npc_sql_overwrites_first_seen_with_canon_session(self):
        sql = load_summaries.canon_npc_sql({
            "name": "Claris",
            "first_seen_session": 6,
            "location": "Thataways",
            "description": "Librarian under the tree.",
            "status": "alive",
        })

        self.assertIn(
            "first_seen_session = COALESCE((SELECT id FROM session WHERE session_number = 6), npc.first_seen_session)",
            sql,
        )
        self.assertNotIn("first_seen_session = COALESCE(npc.first_seen_session", sql)

    def test_canon_npc_sql_can_scrub_unnamed_npc_labels(self):
        sql = load_summaries.canon_npc_sql({
            "name": "Leprechaun thief",
            "first_seen_session": 5,
            "location": "Thataways",
            "description": "Unnamed leprechaun.",
            "status": "fled",
            "is_named": False,
        })

        self.assertIn("'Leprechaun thief'", sql)
        self.assertIn("is_named = FALSE", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 5", sql)

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

    def test_build_sql_scrubs_session05_npcs(self):
        summaries = [
            {
                "session_number": 5,
                "physical_date": "2025-03-30",
                "in_game_date": "1832 AS Apollal 15",
                "title": "The Return to Bentrios",
                "summary": "Baron Wells and a leprechaun appear.",
                "events": ["Baron Wells and a leprechaun appear."],
                "source_path": "session05_summary.md",
                "location": "Bentrios",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Baron Wells'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 1", sql)
        self.assertIn("'Leprechaun thief'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 5", sql)

    def test_build_sql_scrubs_session04_npcs(self):
        summaries = [
            {
                "session_number": 4,
                "physical_date": "2025-03-30",
                "in_game_date": "1832 AS Apollal 14",
                "title": "The Village of Thataways",
                "summary": "A satyr violinist and birdfolk wizard help the party.",
                "events": ["A satyr violinist and birdfolk wizard help the party."],
                "source_path": "session04_summary.md",
                "location": "Thataways",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Satyr violinist'", sql)
        self.assertIn("'Birdfolk wizard'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 4", sql)
        self.assertIn("is_named = FALSE", sql)

    def test_build_sql_scrubs_session03_enemies(self):
        summaries = [
            {
                "session_number": 3,
                "physical_date": "2025-03-30",
                "in_game_date": "1832 AS Apollal 14",
                "title": "The Witch of Thataways",
                "summary": "The party fought a fey witch.",
                "events": ["The party fought a fey witch."],
                "source_path": "session03_summary.md",
                "location": "Thataways",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Fey witch'", sql)
        self.assertIn("'fey_witch'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 3", sql)
        self.assertIn("status_code = 'dead'", sql)
        self.assertIn("Loaded from reviewed canon enemy scrub.", sql)

    def test_build_sql_scrubs_salazar_from_session01(self):
        summaries = [
            {
                "session_number": 1,
                "physical_date": "2025-02-16",
                "in_game_date": "1832 AS Apollal 10",
                "title": "The Battle",
                "summary": "Salazar threatens Baron Wells in Bentrios Tower.",
                "events": ["Salazar threatens Baron Wells in Bentrios Tower."],
                "source_path": "session01_summary.md",
                "location": "Bentrios",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Salazar'", sql)
        self.assertIn("'demon_lord'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 1", sql)
        self.assertIn("Demon Lord of Lightning who threatened Baron Wells", sql)
        self.assertIn("level_code = 'existential'", sql)

    def test_build_sql_includes_travel_confidence_fields(self):
        summaries = [
            {
                "session_number": 5,
                "physical_date": "2025-03-30",
                "in_game_date": "1832 AS Apollal 15",
                "title": "The Return to Bentrios",
                "summary": "The party traveled back to Bentrios.",
                "events": ["The party traveled back to Bentrios."],
                "source_path": "session05_summary.md",
                "location": "Bentrios",
            }
        ]
        travel_logs = [
            {
                "session_number": 5,
                "from_location": "Thataways",
                "to_location": "Bentrios",
                "travel_method": "foot",
                "duration_days": 1,
                "duration_confidence": "high",
                "duration_basis": "Diary dates span Apollal 14 to Apollal 15.",
                "notes": "Party returned to Bentrios.",
                "source": "travel_yaml",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=travel_logs):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("ALTER TABLE travel_log ADD COLUMN IF NOT EXISTS duration_confidence", sql)
        self.assertIn("ALTER TABLE travel_log ADD COLUMN IF NOT EXISTS duration_basis", sql)
        self.assertIn("duration_days, duration_confidence,", sql)
        self.assertIn("'high'", sql)
        self.assertIn("'Diary dates span Apollal 14 to Apollal 15.'", sql)

    def test_build_sql_scrubs_father_joseph_from_earliest_known_session(self):
        summaries = [
            {
                "session_number": 5,
                "physical_date": "2025-03-30",
                "in_game_date": "1832 AS Apollal 15",
                "title": "The Return to Bentrios",
                "summary": "Father Joseph explained the Wells.",
                "events": ["Father Joseph explained the Wells."],
                "source_path": "session05_summary.md",
                "location": "Bentrios",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Father Joseph'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 2", sql)
        self.assertIn("Rage, Salazar, the Wells of Magic", sql)

    def test_build_sql_scrubs_oak_from_session02(self):
        summaries = [
            {
                "session_number": 2,
                "physical_date": "2025-03-02",
                "in_game_date": "1832 AS Apollal 13",
                "title": "Visit to the Temple of Knowledge",
                "summary": "The party meets Oak in the Fey Woods.",
                "events": ["The party meets Oak in the Fey Woods."],
                "source_path": "session02_summary.md",
                "location": "Fey Woods",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Oak'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 2", sql)
        self.assertIn("Dryad of the outer Fey Woods", sql)
        self.assertIn("(SELECT id FROM location WHERE name = 'Fey Woods' LIMIT 1)", sql)

    def test_build_sql_preserves_jennifer_full_name_from_session01(self):
        summaries = [
            {
                "session_number": 1,
                "physical_date": "2025-02-16",
                "in_game_date": "1832 AS Apollal 10",
                "title": "The Battle",
                "summary": "Faban recalls Jennifer Wilbreta.",
                "events": ["Faban recalls Jennifer Wilbreta."],
                "source_path": "session01_summary.md",
                "location": "Bentrios",
            }
        ]

        with patch("load_summaries.load_canon_decisions", return_value={}):
            with patch("load_summaries.load_travel_facts", return_value=[]):
                with patch("load_summaries.load_review_documents", return_value={}):
                    sql = load_summaries.build_sql(summaries)

        self.assertIn("'Jennifer'", sql)
        self.assertIn("'Jennifer Wilbreta'", sql)
        self.assertIn("SELECT id FROM session WHERE session_number = 1", sql)
        self.assertIn("Urgan''s bride", sql)
        self.assertIn("buried his axe", sql)

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
