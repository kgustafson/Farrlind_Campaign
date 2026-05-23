import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import artifact_extractor


class ArtifactExtractorTest(unittest.TestCase):
    def test_extract_json_object_accepts_fenced_json(self):
        document = artifact_extractor.extract_json_object("""```json
{"known_artifact_mentions": [], "new_artifact_candidates": [], "rejected_candidates": [], "uncertainties": []}
```""")
        self.assertEqual(document["known_artifact_mentions"], [])

    def test_postprocess_moves_existing_candidate_to_known_mention(self):
        registry = [{"id": 5, "name": "Acheron Blade", "artifact_type": "weapon", "is_infernal": True}]
        document = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [{
                "proposed_name": "black-bladed rapier",
                "artifact_type": "weapon",
                "description": "Faban's infernal blade.",
                "current_holder": "Faban",
                "is_infernal": True,
                "confidence": "high",
                "evidence": "Faban carries a black-bladed rapier.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(document, registry, "session21", "Faban carries a black-bladed rapier.")

        self.assertEqual(cleaned["new_artifact_candidates"], [])
        self.assertEqual(cleaned["known_artifact_mentions"][0]["artifact_id"], 5)
        self.assertIn("Moved existing artifact candidate", warnings[0])

    def test_postprocess_rejects_candidate_not_in_source(self):
        document = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [{"proposed_name": "Imaginary Wand"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(document, [], "session21", "Only the Acheron Blade is mentioned.")

        self.assertEqual(cleaned["new_artifact_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Imaginary Wand")
        self.assertIn("not present", warnings[0])

    def test_extract_artifacts_writes_review_json(self):
        output = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [{"proposed_name": "Cap of Water Breathing", "description": "Lets Mikani breathe underwater."}],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "knowledge" / "Faban"
            clean = base / "clean"
            raw = base / "raw"
            clean.mkdir(parents=True)
            raw.mkdir()
            (base / "final").mkdir()
            (base / "final" / "session21_summary.md").write_text("Mikani used the Cap of Water Breathing.", encoding="utf-8")
            with patch.object(artifact_extractor, "BASE", base), \
                 patch.object(artifact_extractor, "CLEAN", clean), \
                 patch.object(artifact_extractor, "RAW", raw), \
                 patch.object(artifact_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(artifact_extractor, "load_campaign_metadata", return_value={"party": []}), \
                 patch.object(artifact_extractor, "artifact_registry", return_value=[]), \
                 patch("web_review.services.canon.npc_rows", return_value=[]), \
                 patch("web_review.services.canon.locations", return_value=[]), \
                 patch("raglib.artifact_extractor.generate", return_value=json.dumps(output)):
                path = artifact_extractor.extract_artifacts("session21", model="test-model")

            document = json.loads(path.read_text(encoding="utf-8"))
            metadata = json.loads(path.with_name("session21_artifacts_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(document["new_artifact_candidates"][0]["proposed_name"], "Cap of Water Breathing")
        self.assertEqual(metadata["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
