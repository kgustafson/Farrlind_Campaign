import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.workflow_auto_intake import command_plan, selected_command_plan, watch_queue


class WorkflowAutoIntakeTest(unittest.TestCase):
    def test_command_plan_runs_to_human_review_gate(self):
        with tempfile.TemporaryDirectory() as tmp, patch("scripts.workflow_auto_intake.campaign.raw_dir", return_value=Path(tmp)):
            plan = command_plan(21)

        self.assertEqual([command.step_id for command in plan], [
            "transcribe_audio",
            "diary_source_available",
            "source_status_check",
            "curate_transcript",
            "generate_narrative_summary",
            "extract_session_spine",
            "validate_session_spine",
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
        self.assertEqual(plan[4].argv, [sys.executable, "scripts/rag.py", "generate-narrative-summary", "session21"])
        self.assertEqual(plan[5].argv, [sys.executable, "scripts/rag.py", "extract-session-spine", "session21"])
        self.assertEqual(plan[6].argv, [sys.executable, "scripts/rag.py", "validate-session-spine", "session21"])
        self.assertEqual(plan[7].argv, [sys.executable, "scripts/rag.py", "extract-npcs", "session21"])
        self.assertEqual(plan[8].argv, [sys.executable, "scripts/rag.py", "extract-locations", "session21"])
        self.assertEqual(plan[9].argv, [sys.executable, "scripts/rag.py", "extract-artifacts", "session21"])
        self.assertEqual(plan[10].argv, [sys.executable, "scripts/rag.py", "extract-lore-items", "session21"])
        self.assertEqual(plan[11].argv, [sys.executable, "scripts/rag.py", "extract-combat-encounters", "session21"])
        self.assertEqual(plan[12].argv, [sys.executable, "scripts/rag.py", "extract-open-threads", "session21"])
        self.assertEqual(plan[13].argv, [sys.executable, "scripts/rag.py", "extract", "session21"])
        self.assertEqual(plan[14].argv, [sys.executable, "scripts/rag.py", "postextract", "session21"])
        self.assertIn("summarize_draft", plan[14].completed_steps)

    def test_command_plan_uses_registered_audio_file_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch("scripts.workflow_auto_intake.campaign.raw_dir", return_value=Path(tmp)):
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

    def test_command_plan_preserves_existing_transcript_by_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch("scripts.workflow_auto_intake.campaign.raw_dir", return_value=Path(tmp)):
            (Path(tmp) / "session02_transcript.txt").write_text("existing transcript", encoding="utf-8")

            plan = command_plan(2, "campaigns/trinyvale/audio/session02.mp3")

        self.assertEqual(plan[0].step_id, "transcribe_audio")
        self.assertEqual(plan[0].argv, [])
        self.assertEqual(plan[0].skip_status, "complete")
        self.assertIn("Existing raw transcript preserved", plan[0].skip_comment)

    def test_command_plan_recreates_transcript_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp, patch("scripts.workflow_auto_intake.campaign.raw_dir", return_value=Path(tmp)):
            (Path(tmp) / "session02_transcript.txt").write_text("existing transcript", encoding="utf-8")

            plan = command_plan(2, "campaigns/trinyvale/audio/session02.mp3", "recreate")

        self.assertEqual(
            plan[0].argv,
            [
                sys.executable,
                "scripts/rag.py",
                "transcribe",
                "session02",
                "--audio-file",
                "campaigns/trinyvale/audio/session02.mp3",
            ],
        )

    def test_selected_command_plan_honors_queue_command_subset(self):
        with tempfile.TemporaryDirectory() as tmp, patch("scripts.workflow_auto_intake.campaign.raw_dir", return_value=Path(tmp)):
            plan = selected_command_plan(
                21,
                "",
                "use_existing",
                ["curate_transcript", "extract_npcs", "postextract_shortcut"],
            )

        self.assertEqual([command.step_id for command in plan], [
            "curate_transcript",
            "extract_npcs",
            "postextract_shortcut",
        ])

    def test_watch_queue_polls_without_exiting_after_empty_queue(self):
        with patch("scripts.workflow_auto_intake.process_queue", return_value=0) as process, \
             patch("scripts.workflow_auto_intake.time.sleep") as sleep:
            result = watch_queue(poll_seconds=0, stop_after=2)

        self.assertEqual(result, 0)
        self.assertEqual(process.call_count, 2)
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(sleep.call_args.args[0], 1)
