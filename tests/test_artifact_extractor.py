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

    def test_postprocess_keeps_lantern_paraphrase_grounded_by_source(self):
        document = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [{
                "proposed_name": "Lantern of Green Flame",
                "artifact_type": "tool",
                "description": "A lantern with a black candle that burns green and never runs out.",
                "current_holder": "Jens",
                "evidence": "Jens fishes a lantern out of the soil.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "You get a lantern with a black candle that never runs out and burns with a green flame.",
        )

        self.assertEqual(cleaned["new_artifact_candidates"][0]["proposed_name"], "Lantern of Green Flame")
        self.assertEqual(cleaned["rejected_candidates"], [])
        self.assertEqual(warnings, [])

    def test_postprocess_keeps_trinket_from_soil_paraphrase(self):
        document = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [{
                "proposed_name": "Trinket from the Soil",
                "artifact_type": "trinket",
                "description": "A small trinket found half-buried in the mud.",
                "evidence": "There is something half buried there, and you have found another trinket.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, _warnings = artifact_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "In the soil next to him there is something half buried there, and you have found another trinket.",
        )

        self.assertEqual(cleaned["new_artifact_candidates"][0]["proposed_name"], "Trinket from the Soil")
        self.assertEqual(cleaned["rejected_candidates"], [])

    def test_postprocess_recovers_source_grounded_lantern_from_rejections(self):
        document = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [],
            "rejected_candidates": [{
                "text": "Lantern of Green Flame",
                "reason": "Candidate name not found in session source.",
            }],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "You get a lantern with a black candle that never runs out and burns with a green flame.",
        )

        self.assertEqual(cleaned["new_artifact_candidates"][0]["proposed_name"], "Lantern of Green Flame")
        self.assertEqual(cleaned["rejected_candidates"], [])
        self.assertIn("Recovered source-grounded rejected artifact candidate", warnings[0])

    def test_postprocess_does_not_recover_unrelated_rejected_artifact(self):
        document = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [],
            "rejected_candidates": [{
                "text": "Zombie Envelope",
                "reason": "Candidate name not found in session source.",
            }],
            "uncertainties": [],
        }

        cleaned, _warnings = artifact_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "A zombie clutches an envelope.",
        )

        self.assertEqual(cleaned["new_artifact_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Zombie Envelope")

    def test_postprocess_rejects_party_interpretation_artifact(self):
        document = {
            "known_artifact_mentions": [],
            "new_artifact_candidates": [{
                "proposed_name": "Secret Burger Recipe",
                "description": "The party mistakenly believes the letter points to a secret recipe.",
                "lore_significance": "Only a joke theory.",
                "evidence": "They joke about a secret burger recipe.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(
            document,
            [],
            "session02",
            "The letter mentions the Burgomaster, which the party misreads as Burger Master and jokes about a Secret Burger Recipe.",
        )

        self.assertEqual(cleaned["new_artifact_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Secret Burger Recipe")
        self.assertIn("party-interpretation artifact", warnings[0])

    def test_postprocess_drops_known_artifact_mapped_only_by_model_mention(self):
        registry = [{"id": 2, "name": "Grimoire Mutandi", "artifact_type": "book"}]
        document = {
            "known_artifact_mentions": [{
                "artifact_id": 2,
                "canonical_name": "Grimoire Mutandi",
                "mentioned_as": ["magical chest"],
            }],
            "new_artifact_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(
            document,
            registry,
            "session01",
            "The party placed weapons into a magical chest.",
        )

        self.assertEqual(cleaned["known_artifact_mentions"], [])
        self.assertIn("not present in session source", warnings[0])

    def test_postprocess_converts_unknown_known_mentions_to_new_candidates(self):
        document = {
            "known_artifact_mentions": [{
                "artifact_id": 1,
                "canonical_name": "Magical Chest",
                "new_information": "A golden wooden chest used for storing surrendered items.",
                "artifact_type": "container",
                "current_holder": "unknown",
                "properties": ["materialized from a gemstone and key"],
                "confidence": "high",
                "evidence": "The party placed their belongings into a magical chest.",
            }],
            "new_artifact_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(
            document,
            [],
            "session01",
            "The party placed their belongings into a magical chest.",
        )

        self.assertEqual(cleaned["known_artifact_mentions"], [])
        self.assertEqual(cleaned["new_artifact_candidates"][0]["proposed_name"], "Magical Chest")
        self.assertEqual(cleaned["new_artifact_candidates"][0]["discovered_session"], 1)
        self.assertIn("Converted unknown known artifact mention", warnings[0])

    def test_postprocess_converts_mismatched_known_mentions_to_new_candidates(self):
        registry = [{"id": 2, "name": "Grimoire Mutandi", "artifact_type": "book"}]
        document = {
            "known_artifact_mentions": [{
                "artifact_id": 2,
                "canonical_name": "Magical Chest",
                "new_information": "A golden wooden chest used for storing surrendered items.",
                "artifact_type": "container",
                "current_holder": "unknown",
                "properties": ["materialized from a gemstone and key"],
                "confidence": "high",
                "evidence": "The party placed their belongings into a magical chest.",
            }],
            "new_artifact_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = artifact_extractor.postprocess_extraction(
            document,
            registry,
            "session01",
            "The party placed their belongings into a magical chest.",
        )

        self.assertEqual(cleaned["known_artifact_mentions"], [])
        self.assertEqual(cleaned["new_artifact_candidates"][0]["proposed_name"], "Magical Chest")
        self.assertIn("Converted mismatched known artifact mention", warnings[0])

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
