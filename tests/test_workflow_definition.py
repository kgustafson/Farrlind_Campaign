import unittest
from pathlib import Path

import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[1] / "workflows" / "session_workflow.yaml"


class WorkflowDefinitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
        cls.steps = cls.definition["steps"]
        cls.step_ids = [step["id"] for step in cls.steps]

    def test_workflow_file_has_expected_identity(self):
        workflow = self.definition["workflow"]
        self.assertEqual(workflow["id"], "farrlind_session_canon")
        self.assertEqual(workflow["scope"], "per_session")
        self.assertEqual(workflow["state_persistence"], "database")

    def test_step_ids_are_unique_and_dependencies_exist(self):
        self.assertEqual(len(self.step_ids), len(set(self.step_ids)))
        known = set(self.step_ids)
        for step in self.steps:
            for dependency in step.get("dependencies", []):
                self.assertIn(dependency, known, f"{step['id']} depends on unknown step {dependency}")

    def test_each_step_has_required_operational_fields(self):
        required = {
            "id",
            "display_name",
            "lane",
            "dependencies",
            "expected_inputs",
            "expected_outputs",
            "status_rules",
            "gate",
            "rerun_policy",
            "canon_impact",
        }
        for step in self.steps:
            missing = required - set(step)
            self.assertFalse(missing, f"{step['id']} is missing {sorted(missing)}")

    def test_phase_two_steps_cover_current_pipeline_and_review_commands(self):
        expected = {
            "source_audio_registered",
            "transcribe_audio",
            "diary_source_available",
            "source_status_check",
            "curate_transcript",
            "extract_events",
            "filter_events",
            "classify_events",
            "normalize_events",
            "merge_events",
            "validate_draft",
            "summarize_draft",
            "postextract_shortcut",
            "initialize_review",
            "edit_review_decisions",
            "mark_reviewed",
            "apply_review",
            "write_final_summary",
            "dbload_refresh",
            "run_health",
        }
        self.assertTrue(expected.issubset(set(self.step_ids)))

    def test_definition_includes_lore_verification_and_version_control_closure(self):
        expected = {
            "update_lore_sections",
            "run_tests",
            "web_smoke_check",
            "version_revision_update",
            "git_commit",
            "git_tag",
            "git_push",
        }
        self.assertTrue(expected.issubset(set(self.step_ids)))

    def test_lanes_match_declared_lane_ids(self):
        lanes = {lane["id"] for lane in self.definition["lanes"]}
        for step in self.steps:
            self.assertIn(step["lane"], lanes)


if __name__ == "__main__":
    unittest.main()
