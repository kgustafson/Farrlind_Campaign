import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import open_thread_extractor


class OpenThreadExtractorTest(unittest.TestCase):
    def statuses(self):
        return [
            {"code": "open", "label": "Open"},
            {"code": "resolved", "label": "Resolved"},
            {"code": "superseded", "label": "Superseded"},
            {"code": "unknown", "label": "Unknown"},
        ]

    def types(self):
        return [
            "lore_mystery",
            "active_threat",
            "unresolved_promise",
            "pending_quest",
            "character_hook",
            "faction_tension",
            "canon_ambiguity",
            "dm_foreshadowing",
        ]

    def test_extract_json_object_accepts_fenced_json(self):
        document = open_thread_extractor.extract_json_object("""```json
{"known_thread_mentions": [], "new_thread_candidates": [], "rejected_candidates": [], "uncertainties": []}
```""")
        self.assertEqual(document["known_thread_mentions"], [])

    def test_postprocess_moves_existing_candidate_to_known_mention(self):
        registry = [{"id": 5, "title": "What does the Gale want?", "thread_type": "lore_mystery", "status": "open"}]
        document = {
            "known_thread_mentions": [],
            "new_thread_candidates": [{
                "proposed_title": "What does the Gale want?",
                "thread_type": "active_threat",
                "status": "open",
                "description": "The Gale remains a campaign danger.",
                "confidence": "high",
                "evidence": "The Gale is still ahead.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        with patch("web_review.services.canon.open_thread_statuses", return_value=self.statuses()), \
             patch("web_review.services.canon.open_thread_types", return_value=self.types()):
            cleaned, warnings = open_thread_extractor.postprocess_extraction(document, registry, "session21")

        self.assertEqual(cleaned["new_thread_candidates"], [])
        self.assertEqual(cleaned["known_thread_mentions"][0]["thread_id"], 5)
        self.assertIn("Moved existing open thread candidate", warnings[0])

    def test_postprocess_rejects_candidate_without_title(self):
        document = {
            "known_thread_mentions": [],
            "new_thread_candidates": [{"description": "A title-free fragment."}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        with patch("web_review.services.canon.open_thread_statuses", return_value=self.statuses()), \
             patch("web_review.services.canon.open_thread_types", return_value=self.types()):
            cleaned, warnings = open_thread_extractor.postprocess_extraction(document, [], "session21")

        self.assertEqual(cleaned["new_thread_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "unknown candidate")
        self.assertIn("missing proposed title", warnings[0])

    def test_extract_open_threads_writes_review_json(self):
        output = {
            "known_thread_mentions": [],
            "new_thread_candidates": [{
                "proposed_title": "Niebain Warns Catur Is Already In Danger",
                "thread_type": "active_threat",
                "status": "open",
                "description": "Niebain warned that Catur was already in danger.",
            }],
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
            (base / "final" / "session21_summary.md").write_text("Niebain warned that Catur was already in danger.", encoding="utf-8")
            with patch.object(open_thread_extractor, "BASE", base), \
                 patch.object(open_thread_extractor, "CLEAN", clean), \
                 patch.object(open_thread_extractor, "RAW", raw), \
                 patch.object(open_thread_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(open_thread_extractor, "load_campaign_metadata", return_value={"party": []}), \
                 patch.object(open_thread_extractor, "open_thread_registry", return_value=[]), \
                 patch("web_review.services.canon.locations", return_value=[]), \
                 patch("web_review.services.canon.open_thread_statuses", return_value=self.statuses()), \
                 patch("web_review.services.canon.open_thread_types", return_value=self.types()), \
                 patch("raglib.open_thread_extractor.generate", return_value=json.dumps(output)):
                path = open_thread_extractor.extract_open_threads("session21", model="test-model")

            document = json.loads(path.read_text(encoding="utf-8"))
            metadata = json.loads(path.with_name("session21_open_threads_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(document["new_thread_candidates"][0]["proposed_title"], "Niebain Warns Catur Is Already In Danger")
        self.assertEqual(metadata["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
