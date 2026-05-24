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
            "extract_npcs",
            "extract_locations",
            "extract_artifacts",
            "extract_lore_items",
            "extract_combat_encounters",
            "extract_open_threads",
            "extract_events",
            "postextract_shortcut",
        ])
        self.assertEqual(plan[0].argv, [sys.executable, "scripts/rag.py", "transcribe", "session21"])
        self.assertEqual(plan[3].argv, [sys.executable, "scripts/rag.py", "curate", "session21"])
        self.assertEqual(plan[4].argv, [sys.executable, "scripts/rag.py", "extract-npcs", "session21"])
        self.assertEqual(plan[5].argv, [sys.executable, "scripts/rag.py", "extract-locations", "session21"])
        self.assertEqual(plan[6].argv, [sys.executable, "scripts/rag.py", "extract-artifacts", "session21"])
        self.assertEqual(plan[7].argv, [sys.executable, "scripts/rag.py", "extract-lore-items", "session21"])
        self.assertEqual(plan[8].argv, [sys.executable, "scripts/rag.py", "extract-combat-encounters", "session21"])
        self.assertEqual(plan[9].argv, [sys.executable, "scripts/rag.py", "extract-open-threads", "session21"])
        self.assertEqual(plan[10].argv, [sys.executable, "scripts/rag.py", "extract", "session21"])
        self.assertEqual(plan[11].argv, [sys.executable, "scripts/rag.py", "postextract", "session21"])
        self.assertIn("summarize_draft", plan[11].completed_steps)

    def test_command_plan_uses_registered_audio_file_path(self):
        plan = command_plan(1, "/Volumes/T7_WORK/AI_RAG/campaigns/trinyvale/audio/session01.mp3")

        self.assertEqual(
            plan[0].argv,
            [
                sys.executable,
                "scripts/rag.py",
                "transcribe",
                "session01",
                "--audio-file",
                "/Volumes/T7_WORK/AI_RAG/campaigns/trinyvale/audio/session01.mp3",
            ],
        )
