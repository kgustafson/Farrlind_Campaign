import argparse
import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "dm_query.py"

spec = importlib.util.spec_from_file_location("dm_query", MODULE_PATH)
dm_query = importlib.util.module_from_spec(spec)
sys.modules["dm_query"] = dm_query
spec.loader.exec_module(dm_query)


def args(**overrides):
    values = {
        "container": "farrlind_db",
        "user": "admin",
        "database": "farrlind",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class DmQueryTest(unittest.TestCase):
    def test_sql_literal_escapes_single_quotes(self):
        self.assertEqual(dm_query.sql_literal("Roon's Shield"), "'Roon''s Shield'")

    def test_like_pattern_wraps_and_escapes(self):
        self.assertEqual(dm_query.like_pattern("Catur's coast"), "'%Catur''s coast%'")

    def test_clip_collapses_whitespace_and_truncates(self):
        self.assertEqual(dm_query.clip("a\n  b\tc", 20), "a b c")
        self.assertEqual(dm_query.clip("abcdef", 5), "ab...")

    def test_positive_int_bounds(self):
        self.assertEqual(dm_query.positive_int("12"), 12)
        with self.assertRaises(argparse.ArgumentTypeError):
            dm_query.positive_int("0")
        with self.assertRaises(argparse.ArgumentTypeError):
            dm_query.positive_int("1001")
        with self.assertRaises(argparse.ArgumentTypeError):
            dm_query.positive_int("nope")

    def test_parse_session_ref_accepts_name_or_number(self):
        self.assertEqual(dm_query.parse_session_ref("20"), 20)
        self.assertEqual(dm_query.parse_session_ref("session20"), 20)
        with self.assertRaises(argparse.ArgumentTypeError):
            dm_query.parse_session_ref("session")

    def test_parser_rejects_invalid_limits(self):
        parser = dm_query.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["sessions", "--limit", "-1"])
            with self.assertRaises(SystemExit):
                parser.parse_args(["open-threads", "--recent", "0"])
            with self.assertRaises(SystemExit):
                parser.parse_args(["songs", "--limit", "1001"])

    def test_run_query_invokes_psql_csv_through_docker(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="session_number,title\n20,Catur\n",
            stderr="",
        )
        with patch("dm_query.subprocess.run", return_value=completed) as run:
            rows = dm_query.run_query(args(), "SELECT 1;")

        self.assertEqual(rows, [{"session_number": "20", "title": "Catur"}])
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["docker", "exec", "farrlind_db"])
        self.assertIn("--csv", command)
        self.assertEqual(command[-2:], ["-c", "SELECT 1;"])

    def test_run_query_exits_on_psql_error(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=7,
            stdout="",
            stderr="database down",
        )
        with patch("dm_query.subprocess.run", return_value=completed):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    dm_query.run_query(args(), "SELECT 1;")
        self.assertEqual(raised.exception.code, 7)

    def test_location_query_is_direct_not_summary_broad(self):
        captured_sql = []

        def fake_run_query(_args, sql):
            captured_sql.append(sql)
            return []

        with patch("dm_query.run_query", side_effect=fake_run_query):
            with contextlib.redirect_stdout(io.StringIO()):
                dm_query.location(args(name="Catur"))

        sql = captured_sql[0]
        self.assertIn("e.description ILIKE '%Catur%'", sql)
        self.assertNotIn("s.summary ILIKE", sql)

    def test_topic_query_can_include_summary_context(self):
        captured_sql = []

        def fake_run_query(_args, sql):
            captured_sql.append(sql)
            return []

        with patch("dm_query.run_query", side_effect=fake_run_query):
            dm_query.query_topic_events(args(), "Catur", direct_only=False, limit=12)

        sql = captured_sql[0]
        self.assertIn("s.summary ILIKE '%Catur%'", sql)
        self.assertIn("LIMIT 12", sql)

    def test_context_sessions_searches_session_level_fields(self):
        captured_sql = []

        def fake_run_query(_args, sql):
            captured_sql.append(sql)
            return []

        with patch("dm_query.run_query", side_effect=fake_run_query):
            dm_query.query_context_sessions(args(), "Catur", limit=8)

        sql = captured_sql[0]
        self.assertIn("FROM session s", sql)
        self.assertIn("s.summary ILIKE '%Catur%'", sql)
        self.assertIn("LIMIT 8", sql)

    def test_search_query_requires_all_terms(self):
        captured_sql = []

        def fake_run_query(_args, sql):
            captured_sql.append(sql)
            return []

        with patch("dm_query.run_query", side_effect=fake_run_query):
            with contextlib.redirect_stdout(io.StringIO()):
                dm_query.search(args(terms=["Catur", "shoreline"]))

        sql = captured_sql[0]
        self.assertIn("'%Catur%'", sql)
        self.assertIn("'%shoreline%'", sql)
        self.assertIn(") AND (", sql)

    def test_search_rejects_blank_terms(self):
        with self.assertRaises(SystemExit):
            dm_query.search(args(terms=["", "   "]))

    def test_songs_without_topic_has_no_where_clause(self):
        captured_sql = []

        def fake_run_query(_args, sql):
            captured_sql.append(sql)
            return []

        with patch("dm_query.run_query", side_effect=fake_run_query):
            with contextlib.redirect_stdout(io.StringIO()):
                dm_query.songs(args(topic=None, limit=10))

        self.assertIn("FROM v_songbook", captured_sql[0])
        self.assertNotIn("WHERE title ILIKE", captured_sql[0])

    def test_health_query_collects_counts_and_notes(self):
        captured_sql = []

        def fake_run_query(_args, sql):
            captured_sql.append(sql)
            return [{"sessions_loaded": "21"}]

        with patch.object(dm_query, "run_query", side_effect=fake_run_query):
            row = dm_query.query_health(args())

        self.assertEqual(row["sessions_loaded"], "21")
        sql = captured_sql[0]
        self.assertIn("sessions_with_transcripts", sql)
        self.assertIn("songs_missing_prompts", sql)
        self.assertIn("primary_location_mismatches", sql)

    def test_health_prints_rollup_and_data_notes(self):
        health_row = {
            "sessions_loaded": "21",
            "sessions_with_summaries": "21",
            "events_loaded": "140",
            "songs_loaded": "26",
            "songs_with_prompts": "23",
            "songs_missing_prompt_count": "3",
            "latest_session_number": "20",
            "latest_session_title": "Salt, Steel",
            "transcript_sessions": "19, 20",
            "songs_missing_prompts": "12. The Day We Called It Victory; 23. The Hand That Did Not Open",
            "location_mismatch_notes": "Session 20 primary location is Balrog, but event locations include Catur",
        }
        canon = {
            "session_primary_locations": [
                {
                    "session": "session20",
                    "canonical": "Coast near Catur",
                    "status": "needs_db_update",
                    "decision": "Primary location is the coast near Catur.",
                }
            ],
            "event_review_decisions": [
                {
                    "session": "session20",
                    "status": "needs_db_update",
                    "decision_type": "missing_primary_event",
                    "description": "The party negotiated with fishermen for a vessel.",
                }
            ],
        }

        with patch("dm_query.query_health", return_value=health_row):
            with patch("dm_query.load_canon_decisions", return_value=canon):
                with patch("dm_query.applied_review_session_numbers", return_value=set()):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        dm_query.health(args())

        rendered = output.getvalue()
        self.assertIn("DM Query Health", rendered)
        self.assertIn("Sessions loaded: 21", rendered)
        self.assertIn("Latest session: 20 - Salt, Steel", rendered)
        self.assertIn("Song missing prompt: 12. The Day We Called It Victory", rendered)
        self.assertNotIn("Session 20 primary location is Balrog", rendered)
        self.assertIn("Canon Decisions", rendered)
        self.assertIn("session20 primary location -> Coast near Catur", rendered)
        self.assertIn("session20 missing_primary_event", rendered)

    def test_health_suppresses_location_mismatch_for_applied_review_sessions(self):
        health_row = {
            "sessions_loaded": "21",
            "sessions_with_summaries": "21",
            "events_loaded": "140",
            "songs_loaded": "26",
            "songs_with_prompts": "23",
            "songs_missing_prompt_count": "3",
            "latest_session_number": "20",
            "latest_session_title": "Salt, Steel",
            "transcript_sessions": "19, 20",
            "songs_missing_prompts": "",
            "location_mismatch_notes": "Session 17 primary location is Paramon, but event locations include Balrog, Crossroads",
        }

        with patch("dm_query.query_health", return_value=health_row):
            with patch("dm_query.load_canon_decisions", return_value={}):
                with patch("dm_query.applied_review_session_numbers", return_value={17}):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        dm_query.health(args())

        rendered = output.getvalue()
        self.assertIn("No obvious data notes.", rendered)
        self.assertNotIn("Session 17 primary location", rendered)

    def test_note_session_number_parses_health_notes(self):
        self.assertEqual(
            dm_query.note_session_number("Session 20 primary location is Coast near Catur"),
            20,
        )
        self.assertIsNone(dm_query.note_session_number("Song missing prompt: 12. Title"))

    def test_load_canon_decisions_missing_file_returns_empty(self):
        missing = ROOT / "does-not-exist.yaml"
        self.assertEqual(dm_query.load_canon_decisions(missing), {})

    def test_format_canon_decisions_handles_known_sections(self):
        decisions = {
            "session_primary_locations": [
                {
                    "session": "session20",
                    "canonical": "Coast near Catur",
                    "status": "needs_db_update",
                    "decision": "Primary location is the coast near Catur.",
                }
            ],
            "event_review_decisions": [
                {
                    "session": "session20",
                    "status": "needs_db_update",
                    "decision_type": "missing_primary_event",
                    "description": "Negotiated with fishermen for a vessel.",
                }
            ],
        }

        notes = dm_query.format_canon_decisions(decisions)

        self.assertEqual(len(notes), 2)
        self.assertIn("session20 primary location -> Coast near Catur", notes[0])
        self.assertIn("session20 missing_primary_event", notes[1])

    def test_canon_decisions_for_session_filters_by_session_key(self):
        decisions = {
            "session_primary_locations": [
                {"session": "session19", "canonical": "Balrog"},
                {"session": "session20", "canonical": "Coast near Catur"},
            ],
            "event_review_decisions": [
                {"session": "session20", "description": "Missing event"},
            ],
        }

        filtered = dm_query.canon_decisions_for_session(decisions, 20)

        self.assertEqual(len(filtered["session_primary_locations"]), 1)
        self.assertEqual(filtered["session_primary_locations"][0]["canonical"], "Coast near Catur")
        self.assertEqual(len(filtered["event_review_decisions"]), 1)

    def test_applied_review_session_numbers_reads_applied_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            applied = Path(tmp) / "session17_review.yaml"
            draft = Path(tmp) / "session18_review.yaml"
            applied.write_text(yaml.safe_dump({"session": "session17", "status": "applied"}), encoding="utf-8")
            draft.write_text(yaml.safe_dump({"session": "session18", "status": "reviewed"}), encoding="utf-8")

            self.assertEqual(dm_query.applied_review_session_numbers([applied, draft]), {17})

    def test_build_review_document_uses_pending_decisions(self):
        session = {
            "session_number": "20",
            "title": "Salt, Steel",
            "session_date": "2026-04-27",
            "in_game_date": "1832 AS Namal 20",
            "location": "Coast near Catur",
        }
        events = [
            {
                "sequence_order": "1",
                "event_type": "travel",
                "location": "Coast near Catur",
                "description": "Arrived at Catur shoreline",
                "significance": "4",
            }
        ]

        document = dm_query.build_review_document(session, events)

        self.assertEqual(document["session"], "session20")
        self.assertEqual(document["status"], "in_review")
        self.assertEqual(document["items"][0]["id"], "event-001")
        self.assertEqual(document["items"][0]["sequence"], 1)
        self.assertEqual(document["items"][0]["decision"], "pending")
        self.assertEqual(document["items"][0]["applied_status"], "pending")
        self.assertIn("Use sequence", document["review_instructions"][2])
        self.assertEqual(document["added_items"], [])

    def test_init_review_writes_yaml_and_refuses_overwrite(self):
        review_data = {
            "session": {
                "session_number": "20",
                "session_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "location": "Coast near Catur",
                "summary": "The party arrived near Catur.",
            },
            "events": [
                {
                    "sequence_order": "1",
                    "event_type": "travel",
                    "location": "Coast near Catur",
                    "description": "Arrived at Catur shoreline",
                    "significance": "4",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "session20_review.yaml"
            with patch("dm_query.query_event_review", return_value=review_data):
                with patch("dm_query.review_path", return_value=output_path):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        dm_query.init_review(args(session_number=20))
                    with self.assertRaises(SystemExit):
                        dm_query.init_review(args(session_number=20))

            written = output_path.read_text(encoding="utf-8")
            self.assertIn("session: session20", written)
            self.assertIn("sequence: 1", written)
            self.assertIn("decision: pending", written)
            self.assertIn("Wrote", output.getvalue())

    def test_summarize_review_counts_decisions_and_applied_status(self):
        document = {
            "session": "session20",
            "status": "in_review",
            "session_title": "Salt, Steel",
            "items": [
                {"decision": "pending", "applied_status": "pending"},
                {"decision": "accepted", "applied_status": "applied"},
                {"decision": "corrected", "applied_status": "pending"},
                {"decision": "rejected", "applied_status": "pending"},
            ],
            "added_items": [
                {"decision": "added", "applied_status": "pending"},
            ],
        }

        summary = dm_query.summarize_review(document, Path("session20_review.yaml"))

        self.assertEqual(summary["session"], "session20")
        self.assertEqual(summary["total_items"], 5)
        self.assertEqual(summary["base_items"], 4)
        self.assertEqual(summary["added_items"], 1)
        self.assertEqual(summary["decisions"]["pending"], 1)
        self.assertEqual(summary["decisions"]["accepted"], 1)
        self.assertEqual(summary["decisions"]["corrected"], 1)
        self.assertEqual(summary["decisions"]["rejected"], 1)
        self.assertEqual(summary["decisions"]["added"], 1)
        self.assertEqual(summary["applied"]["applied"], 1)
        self.assertEqual(summary["applied"]["pending"], 4)

    def test_mark_review_applied_updates_statuses(self):
        document = {
            "session": "session20",
            "status": "reviewed",
            "items": [
                {"decision": "accepted", "applied_status": "pending"},
                {"decision": "rejected", "applied_status": "pending"},
            ],
            "added_items": [
                {"decision": "added", "applied_status": "pending"},
            ],
        }

        updated = dm_query.mark_review_applied(document, "2026-05-04")

        self.assertEqual(updated["status"], "applied")
        self.assertEqual(updated["applied_on"], "2026-05-04")
        self.assertTrue(all(item["applied_status"] == "applied" for item in updated["items"]))
        self.assertEqual(updated["added_items"][0]["applied_on"], "2026-05-04")

    def test_review_has_pending_decisions(self):
        self.assertTrue(dm_query.review_has_pending_decisions({"items": [{"decision": "pending"}]}))
        self.assertFalse(dm_query.review_has_pending_decisions({"items": [{"decision": "accepted"}]}))

    def test_review_next_action_reports_edit_for_pending_or_unknown_decisions(self):
        summary = dm_query.summarize_review(
            {
                "session": "session20",
                "status": "in_review",
                "items": [
                    {"decision": "pending", "applied_status": "pending"},
                    {"decision": "acc", "applied_status": "pending"},
                ],
            },
            Path("/tmp/session20_review.yaml"),
        )

        action, detail = dm_query.review_next_action(summary)

        self.assertEqual(action, "edit")
        self.assertIn("1 pending", detail)
        self.assertIn("1 unknown", detail)

    def test_review_next_action_reports_apply_for_completed_unapplied_review(self):
        summary = dm_query.summarize_review(
            {
                "session": "session20",
                "status": "reviewed",
                "items": [{"decision": "accepted", "applied_status": "pending"}],
            },
            Path("/tmp/session20_review.yaml"),
        )

        action, detail = dm_query.review_next_action(summary)

        self.assertEqual(action, "apply")
        self.assertIn("apply-review session20", detail)

    def test_review_next_action_reports_done_for_applied_review(self):
        summary = dm_query.summarize_review(
            {
                "session": "session20",
                "status": "applied",
                "items": [{"decision": "accepted", "applied_status": "applied"}],
            },
            Path("/tmp/session20_review.yaml"),
        )

        action, detail = dm_query.review_next_action(summary)

        self.assertEqual(action, "done")
        self.assertIn("applied", detail)

    def test_review_status_prints_review_file_counts(self):
        document = {
            "session": "session20",
            "status": "in_review",
            "session_title": "Salt, Steel",
            "items": [{"decision": "pending", "applied_status": "pending"}],
            "added_items": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session20_review.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            with patch("dm_query.discover_review_files", return_value=[path]):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    dm_query.review_status(args())

        rendered = output.getvalue()
        self.assertIn("Review Status", rendered)
        self.assertIn("session20: in_review", rendered)
        self.assertIn("pending=1", rendered)

    def test_review_status_handles_no_review_files(self):
        with patch("dm_query.discover_review_files", return_value=[]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                dm_query.review_status(args())

        self.assertIn("No review files found.", output.getvalue())

    def test_review_next_prints_init_for_missing_session_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session21_review.yaml"
            with patch("dm_query.review_path", return_value=path):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    dm_query.review_next(args(session_number=21))

        rendered = output.getvalue()
        self.assertIn("session21: init", rendered)
        self.assertIn("init-review session21", rendered)

    def test_review_next_prints_actions_for_discovered_reviews(self):
        document = {
            "session": "session20",
            "status": "reviewed",
            "session_title": "Salt, Steel",
            "items": [{"decision": "accepted", "applied_status": "pending"}],
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session20_review.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            with patch("dm_query.discover_review_files", return_value=[path]):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    dm_query.review_next(args(session_number=None))

        rendered = output.getvalue()
        self.assertIn("session20: apply", rendered)
        self.assertIn("Salt, Steel", rendered)
        self.assertIn("apply-review session20", rendered)

    def test_apply_review_refuses_pending_review(self):
        document = {
            "session": "session20",
            "status": "in_review",
            "items": [{"decision": "pending", "applied_status": "pending"}],
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session20_review.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            with patch("dm_query.review_path", return_value=path):
                with self.assertRaises(SystemExit) as raised:
                    dm_query.apply_review(args(session_number=20, applied_on="2026-05-04"))

        self.assertIn("pending decisions", str(raised.exception))

    def test_apply_review_runs_dbload_and_marks_applied(self):
        document = {
            "session": "session20",
            "status": "reviewed",
            "items": [{"decision": "accepted", "applied_status": "pending"}],
            "added_items": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session20_review.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            completed = subprocess.CompletedProcess(args=[], returncode=0)
            with patch("dm_query.review_path", return_value=path):
                with patch("dm_query.subprocess.run", return_value=completed) as run:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        dm_query.apply_review(args(session_number=20, applied_on="2026-05-04"))

            updated = yaml.safe_load(path.read_text(encoding="utf-8"))

        self.assertEqual(updated["status"], "applied")
        self.assertEqual(updated["items"][0]["applied_status"], "applied")
        self.assertIn("Applied review", output.getvalue())
        self.assertEqual(run.call_args.args[0][-2:], ["dbload", "--apply"])

    def test_review_events_prints_db_and_pending_canon_decisions(self):
        review_data = {
            "session": {
                "session_number": "20",
                "session_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "location": "Balrog",
                "summary": "The party arrived near Catur.",
            },
            "events": [
                {
                    "sequence_order": "1",
                    "event_type": "travel",
                    "location": "Catur",
                    "description": "Arrived at Catur shoreline",
                    "significance": "4",
                }
            ],
        }
        canon = {
            "session_primary_locations": [
                {
                    "session": "session20",
                    "canonical": "Coast near Catur",
                    "status": "needs_db_update",
                    "decision": "Primary location is the coast near Catur.",
                }
            ],
            "event_review_decisions": [
                {
                    "session": "session20",
                    "event_type": "social",
                    "significance": 4,
                    "status": "needs_db_update",
                    "description": "The party negotiated with fishermen for a vessel.",
                    "canon_notes": ["Locathah were mentioned."],
                }
            ],
        }

        with patch("dm_query.query_event_review", return_value=review_data):
            with patch("dm_query.load_canon_decisions", return_value=canon):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    dm_query.review_events(args(session_number=20))

        rendered = output.getvalue()
        self.assertIn("Session 20 Event Review", rendered)
        self.assertIn("Current DB Events", rendered)
        self.assertIn("Arrived at Catur shoreline", rendered)
        self.assertIn("Coast near Catur", rendered)
        self.assertIn("negotiated with fishermen", rendered)

    def test_session_final_prints_reviewed_packet(self):
        review_data = {
            "session": {
                "session_number": "20",
                "session_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "location": "Coast near Catur",
                "summary": "The party arrived near Catur.",
            },
            "events": [
                {
                    "sequence_order": "1",
                    "event_type": "travel",
                    "location": "Coast near Catur",
                    "description": "Arrived at Catur shoreline",
                    "significance": "4",
                }
            ],
        }
        document = {
            "session": "session20",
            "status": "applied",
            "applied_on": "2026-05-04",
            "items": [
                {
                    "decision": "accepted",
                    "source_text": "Arrived at Catur shoreline",
                    "event_type": "travel",
                    "location": "Coast near Catur",
                },
                {
                    "decision": "rejected",
                    "source_text": "Roon continues to survive against all odds",
                    "event_type": "discovery",
                    "location": "Coast near Catur",
                    "reason": "Not a session event.",
                },
            ],
            "added_items": [],
        }
        canon = {
            "session_primary_locations": [
                {
                    "session": "session20",
                    "canonical": "Coast near Catur",
                    "status": "applied",
                    "decision": "Primary location is the coast near Catur.",
                }
            ],
            "event_review_decisions": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session20_review.yaml"
            path.write_text(yaml.safe_dump(document), encoding="utf-8")
            with patch("dm_query.query_event_review", return_value=review_data):
                with patch("dm_query.review_path", return_value=path):
                    with patch("dm_query.load_canon_decisions", return_value=canon):
                        with contextlib.redirect_stdout(io.StringIO()) as output:
                            dm_query.session_final(args(session_number=20))

        rendered = output.getvalue()
        self.assertIn("Session 20 Final", rendered)
        self.assertIn("Review status: applied", rendered)
        self.assertIn("Final DB Events", rendered)
        self.assertIn("Arrived at Catur shoreline", rendered)
        self.assertIn("Accepted / Corrected / Added Decisions", rendered)
        self.assertIn("Rejected Decisions", rendered)
        self.assertIn("Roon continues", rendered)
        self.assertIn("Canon Decisions", rendered)
        self.assertIn("Primary location is the coast near Catur", rendered)
        self.assertIn("Ingest Draft Summary", rendered)

    def test_session_final_exits_when_session_missing(self):
        with patch("dm_query.query_event_review", return_value={"session": {}, "events": []}):
            with self.assertRaises(SystemExit) as raised:
                dm_query.session_final(args(session_number=20))

        self.assertIn("No session found", str(raised.exception))

    def test_render_final_summary_uses_final_events_and_excluded_items(self):
        session = {
            "session_date": "2026-04-27",
            "in_game_date": "1832 AS Namal 20",
            "title": "Salt, Steel",
            "location": "Coast near Catur",
        }
        events = [
            {
                "event_type": "travel",
                "location": "Coast near Catur",
                "description": "Arrived at Catur shoreline",
            }
        ]
        review_document = {
            "status": "applied",
            "applied_on": "2026-05-04",
            "items": [
                {
                    "decision": "rejected",
                    "source_text": "Roon continues to survive against all odds",
                    "reason": "Not a session event.",
                }
            ],
        }
        decisions = {
            "session_primary_locations": [
                {
                    "canonical": "Coast near Catur",
                    "status": "applied",
                    "decision": "Primary location is the coast near Catur.",
                }
            ],
            "event_review_decisions": [],
        }

        rendered = dm_query.render_final_summary(session, events, review_document, decisions, 20)

        self.assertIn("# Session 20: Salt, Steel", rendered)
        self.assertIn("## Canon Events", rendered)
        self.assertIn("Arrived at Catur shoreline", rendered)
        self.assertIn("## Excluded Draft Items", rendered)
        self.assertIn("Roon continues", rendered)
        self.assertIn("The ingest draft summary is source material, not canon.", rendered)

    def test_write_final_summary_writes_canon_file(self):
        review_data = {
            "session": {
                "session_number": "20",
                "session_date": "2026-04-27",
                "in_game_date": "1832 AS Namal 20",
                "title": "Salt, Steel",
                "location": "Coast near Catur",
                "summary": "Draft summary with Roon.",
            },
            "events": [
                {
                    "sequence_order": "1",
                    "event_type": "travel",
                    "location": "Coast near Catur",
                    "description": "Arrived at Catur shoreline",
                    "significance": "4",
                }
            ],
        }
        document = {
            "session": "session20",
            "status": "applied",
            "applied_on": "2026-05-04",
            "items": [],
            "added_items": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "session20_review.yaml"
            output_path = Path(tmp) / "session20_summary.md"
            review_path.write_text(yaml.safe_dump(document), encoding="utf-8")
            with patch("dm_query.query_event_review", return_value=review_data):
                with patch("dm_query.review_path", return_value=review_path):
                    with patch("dm_query.final_summary_path", return_value=output_path):
                        with patch("dm_query.load_canon_decisions", return_value={}):
                            with contextlib.redirect_stdout(io.StringIO()) as output:
                                dm_query.write_final_summary(args(session_number=20))

            written = output_path.read_text(encoding="utf-8")

        self.assertIn("Wrote", output.getvalue())
        self.assertIn("Canon Events", written)
        self.assertIn("Arrived at Catur shoreline", written)
        self.assertNotIn("Draft summary with Roon", written)

    def test_write_final_summary_requires_applied_review(self):
        review_data = {
            "session": {"session_number": "20", "title": "Salt, Steel"},
            "events": [],
        }
        document = {"session": "session20", "status": "reviewed"}

        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "session20_review.yaml"
            review_path.write_text(yaml.safe_dump(document), encoding="utf-8")
            with patch("dm_query.query_event_review", return_value=review_data):
                with patch("dm_query.review_path", return_value=review_path):
                    with self.assertRaises(SystemExit) as raised:
                        dm_query.write_final_summary(args(session_number=20))

        self.assertIn("Review must be applied", str(raised.exception))

    def test_parser_accepts_health_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["health"])
        self.assertEqual(parsed.func, dm_query.health)

    def test_parser_accepts_review_events_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["review-events", "session20"])
        self.assertEqual(parsed.func, dm_query.review_events)
        self.assertEqual(parsed.session_number, 20)

    def test_parser_accepts_init_review_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["init-review", "session20"])
        self.assertEqual(parsed.func, dm_query.init_review)
        self.assertEqual(parsed.session_number, 20)

    def test_parser_accepts_apply_review_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["apply-review", "session20", "--applied-on", "2026-05-04"])
        self.assertEqual(parsed.func, dm_query.apply_review)
        self.assertEqual(parsed.session_number, 20)
        self.assertEqual(parsed.applied_on, "2026-05-04")

    def test_parser_accepts_review_status_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["review-status"])
        self.assertEqual(parsed.func, dm_query.review_status)

    def test_parser_accepts_review_next_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["review-next", "session20"])
        self.assertEqual(parsed.func, dm_query.review_next)
        self.assertEqual(parsed.session_number, 20)

    def test_parser_accepts_session_final_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["session-final", "session20"])
        self.assertEqual(parsed.func, dm_query.session_final)
        self.assertEqual(parsed.session_number, 20)

    def test_parser_accepts_write_final_summary_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["write-final-summary", "session20"])
        self.assertEqual(parsed.func, dm_query.write_final_summary)
        self.assertEqual(parsed.session_number, 20)

    def test_print_prep_questions_uses_topic_signals(self):
        topic_events = [{"description": "Met fishermen — boats missing, lights under water"}]
        open_rows = [{"description": "The Wand of Wells and cataclysm remain unresolved"}]

        with contextlib.redirect_stdout(io.StringIO()) as output:
            dm_query.print_prep_questions("Catur", topic_events, open_rows)

        rendered = output.getvalue()
        self.assertIn("Prep Questions", rendered)
        self.assertIn("stranger than it looks", rendered)
        self.assertIn("Wand of Wells", rendered)

    def test_brief_composes_subqueries(self):
        calls = []

        def fake_run_query(_args, sql):
            calls.append(sql)
            return []

        with patch("dm_query.run_query", side_effect=fake_run_query):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                dm_query.brief(args(topic="Catur"))

        self.assertEqual(len(calls), 5)
        rendered = output.getvalue()
        self.assertIn("Catur Prep Brief", rendered)
        self.assertIn("Direct Topic Facts", rendered)
        self.assertIn("Broader Topic Context", rendered)
        self.assertIn("Open Threads", rendered)
        self.assertIn("Prep Questions", rendered)
        self.assertIn("Related Songs", rendered)


if __name__ == "__main__":
    unittest.main()
