import unittest

from raglib.workflow_state import (
    historical_step_state,
    historical_workflow_seed_sql,
    initialize_workflow_sql,
    load_workflow_definition,
    parse_session_number,
    render_session_refs,
    session_name,
    workflow_state_schema_sql,
)


class WorkflowStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition = load_workflow_definition()
        cls.sql = initialize_workflow_sql("session21", cls.definition)

    def test_session_references_parse_to_numbers(self):
        self.assertEqual(parse_session_number("session00"), 0)
        self.assertEqual(parse_session_number("session21"), 21)
        self.assertEqual(parse_session_number("session021"), 21)
        self.assertEqual(parse_session_number("21"), 21)
        self.assertEqual(session_name(0), "session00")
        self.assertEqual(session_name(21), "session21")

    def test_rejects_invalid_session_reference(self):
        with self.assertRaises(ValueError):
            parse_session_number("chapter21")

    def test_session_template_values_are_rendered_recursively(self):
        value = {
            "command": "./rag-env/bin/python scripts/rag.py status sessionXX",
            "paths": ["audio/sessionXX.wav"],
        }
        self.assertEqual(
            render_session_refs(value, "session21"),
            {
                "command": "./rag-env/bin/python scripts/rag.py status session21",
                "paths": ["audio/session21.wav"],
            },
        )

    def test_schema_tracks_required_runtime_state_fields(self):
        schema = workflow_state_schema_sql()
        required_fields = [
            "workflow_run",
            "workflow_step_state",
            "started_at",
            "completed_at",
            "summary_comment",
            "inputs",
            "outputs",
            "dependencies",
            "status_rules",
        ]
        for field in required_fields:
            self.assertIn(field, schema)

    def test_initialize_sql_creates_session_workflow_and_ordered_steps(self):
        self.assertIn("INSERT INTO session", self.sql)
        self.assertIn("INSERT INTO workflow_run", self.sql)
        self.assertIn("INSERT INTO workflow_step_state", self.sql)
        self.assertIn("ON CONFLICT (session_id, workflow_id, workflow_version)", self.sql)
        self.assertIn("'farrlind_session_canon'", self.sql)
        self.assertIn("'source_audio_registered', 1", self.sql)
        self.assertIn("'extract_npcs', 7", self.sql)
        self.assertIn("'extract_open_threads', 12", self.sql)
        self.assertIn("'review_npc_extraction', 20", self.sql)
        self.assertIn("'initialize_review', 26", self.sql)
        self.assertIn("'git_push', 39", self.sql)

    def test_initialize_sql_uses_rendered_session_inputs_outputs_and_commands(self):
        self.assertIn("audio/session21.wav", self.sql)
        self.assertIn("campaigns/farrlind/raw/session21_transcript.txt", self.sql)
        self.assertIn("./rag-env/bin/python scripts/rag.py transcribe session21", self.sql)
        self.assertNotIn("sessionXX", self.sql)

    def test_step_count_matches_workflow_definition(self):
        expected_rows = len(self.definition["steps"])
        actual_rows = self.sql.count("::jsonb")
        self.assertGreaterEqual(actual_rows, expected_rows * 4)

    def test_historical_seed_sql_marks_range_and_estimates_history(self):
        sql = historical_workflow_seed_sql(0, 1, self.definition)
        self.assertIn("Historical timestamps are estimated", sql)
        self.assertIn("session_number = 0", sql)
        self.assertIn("session_number = 1", sql)
        self.assertIn("timestamp_estimate", sql)
        self.assertIn("workflow_step_state", sql)

    def test_historical_seed_marks_older_missing_audio_as_not_applicable(self):
        source_step = next(step for step in self.definition["steps"] if step["id"] == "source_audio_registered")
        state = historical_step_state(0, source_step)
        self.assertEqual(state["status"], "not_applicable")
        self.assertIn("No preserved audio", state["comment"])

    def test_historical_seed_marks_existing_review_as_complete(self):
        review_step = next(step for step in self.definition["steps"] if step["id"] == "apply_review")
        state = historical_step_state(20, review_step)
        self.assertEqual(state["status"], "complete")


if __name__ == "__main__":
    unittest.main()
