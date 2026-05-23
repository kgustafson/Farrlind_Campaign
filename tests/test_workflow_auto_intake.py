import sys
import unittest

from scripts.workflow_auto_intake import command_plan


class WorkflowAutoIntakeTest(unittest.TestCase):
    def test_command_plan_runs_to_human_review_gate(self):
        plan = command_plan(21)

        self.assertEqual([command.step_id for command in plan], [
            "transcribe_audio",
            "diary_source_available",
            "source_status_check",
            "curate_transcript",
            "extract_events",
            "postextract_shortcut",
            "initialize_review",
        ])
        self.assertEqual(plan[0].argv, [sys.executable, "scripts/rag.py", "transcribe", "session21"])
        self.assertEqual(plan[3].argv, [sys.executable, "scripts/rag.py", "curate", "session21"])
        self.assertEqual(plan[4].argv, [sys.executable, "scripts/rag.py", "extract", "session21"])
        self.assertEqual(plan[5].argv, [sys.executable, "scripts/rag.py", "postextract", "session21"])
        self.assertEqual(plan[6].argv, [sys.executable, "scripts/dm_query.py", "init-review", "session21"])
        self.assertIn("summarize_draft", plan[5].completed_steps)
