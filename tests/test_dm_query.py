import argparse
import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


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

        with patch("dm_query.query_health", return_value=health_row):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                dm_query.health(args())

        rendered = output.getvalue()
        self.assertIn("DM Query Health", rendered)
        self.assertIn("Sessions loaded: 21", rendered)
        self.assertIn("Latest session: 20 - Salt, Steel", rendered)
        self.assertIn("Song missing prompt: 12. The Day We Called It Victory", rendered)
        self.assertIn("Session 20 primary location is Balrog", rendered)

    def test_parser_accepts_health_command(self):
        parser = dm_query.build_parser()
        parsed = parser.parse_args(["health"])
        self.assertEqual(parsed.func, dm_query.health)

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
