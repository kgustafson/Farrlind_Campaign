import unittest

from raglib.workflow_state import (
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
        self.assertEqual(parse_session_number("session21"), 21)
        self.assertEqual(parse_session_number("session021"), 21)
        self.assertEqual(parse_session_number("21"), 21)
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
        self.assertIn("'git_push', 26", self.sql)

    def test_initialize_sql_uses_rendered_session_inputs_outputs_and_commands(self):
        self.assertIn("audio/session21.wav", self.sql)
        self.assertIn("knowledge/Faban/raw/session21_transcript.txt", self.sql)
        self.assertIn("./rag-env/bin/python scripts/rag.py transcribe session21", self.sql)
        self.assertNotIn("sessionXX", self.sql)

    def test_step_count_matches_workflow_definition(self):
        expected_rows = len(self.definition["steps"])
        actual_rows = self.sql.count("::jsonb")
        self.assertGreaterEqual(actual_rows, expected_rows * 4)


if __name__ == "__main__":
    unittest.main()
