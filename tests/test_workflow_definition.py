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
            "generate_narrative_summary",
            "extract_session_spine",
            "validate_session_spine",
            "extract_events",
            "extract_npcs",
            "extract_locations",
            "extract_artifacts",
            "extract_lore_items",
            "extract_combat_encounters",
            "extract_open_threads",
            "filter_events",
            "classify_events",
            "normalize_events",
            "merge_events",
            "validate_draft",
            "summarize_draft",
            "postextract_shortcut",
            "review_npc_extraction",
            "review_location_extraction",
            "review_artifact_extraction",
            "review_lore_item_extraction",
            "review_combat_encounter_extraction",
            "review_open_thread_extraction",
            "initialize_review",
            "edit_review_decisions",
            "mark_reviewed",
            "apply_review",
            "write_final_summary",
            "dbload_refresh",
            "run_health",
        }
        self.assertTrue(expected.issubset(set(self.step_ids)))

    def test_entity_extractors_run_before_human_review(self):
        by_id = {step["id"]: step for step in self.steps}
        expected_extractors = {
            "extract_npcs": "extract-npcs",
            "extract_locations": "extract-locations",
            "extract_artifacts": "extract-artifacts",
            "extract_lore_items": "extract-lore-items",
            "extract_combat_encounters": "extract-combat-encounters",
            "extract_open_threads": "extract-open-threads",
        }
        for step_id, command_name in expected_extractors.items():
            self.assertEqual(by_id[step_id]["lane"], "entity_extraction")
            self.assertIn("validate_session_spine", by_id[step_id]["dependencies"])
            self.assertIn(command_name, by_id[step_id]["command"])

        self.assertIn("extract_session_spine", by_id["validate_session_spine"]["dependencies"])
        for step_id in expected_extractors:
            self.assertIn(step_id, by_id["extract_events"]["dependencies"])

        review_dependencies = {
            "review_npc_extraction": "extract_npcs",
            "review_location_extraction": "extract_locations",
            "review_artifact_extraction": "extract_artifacts",
            "review_lore_item_extraction": "extract_lore_items",
            "review_combat_encounter_extraction": "extract_combat_encounters",
            "review_open_thread_extraction": "extract_open_threads",
        }
        for review_step, extractor_step in review_dependencies.items():
            self.assertEqual(by_id[review_step]["lane"], "human_review")
            self.assertIn(extractor_step, by_id[review_step]["dependencies"])
            self.assertIn(review_step, by_id["initialize_review"]["dependencies"])

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
