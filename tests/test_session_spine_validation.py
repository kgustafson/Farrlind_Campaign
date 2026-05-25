import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from raglib import session_spine, session_spine_validation


class SessionSpineValidationTest(unittest.TestCase):
    def test_validate_session_spine_writes_report_from_allowed_sources(self):
        spine = {
            "session": "session02",
            "timeline": {
                "starting_location": "Svalich Road",
                "ending_location": "Blood on the Vine",
                "real_world_date": "N/A",
                "in_world_date": "N/A",
            },
            "major_events": [
                {
                    "order": 1,
                    "title": "Road Corpses",
                    "event_type": "discovery",
                    "location": "Svalich Road",
                    "summary": "The party finds dead messengers beside the road.",
                    "party_members": ["Jens"],
                    "npcs": [],
                    "entities": ["dead messengers"],
                    "items": ["letter"],
                    "party_interpretation": "",
                    "outcome": "The bodies rise as zombies.",
                    "evidence": "Narrative road discovery.",
                    "needs_review": [],
                }
            ],
        }
        narrative = """# Session Narrative Draft

## Chronological Major Events

- The party finds dead messengers along Svalich Road.
- They discover a black candle lantern burning with green flame.
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            raw = root / "raw"
            clean.mkdir()
            raw.mkdir()
            (clean / "session02_spine.yaml").write_text(yaml.safe_dump(spine), encoding="utf-8")
            (clean / "session02_narrative.md").write_text(narrative, encoding="utf-8")
            (clean / "session02_curated.md").write_text("Road corpses and a letter.", encoding="utf-8")
            (raw / "session02_transcript.txt").write_text(
                "On Svalich Road they find bodies. Later there is a black candle lantern with green flame.",
                encoding="utf-8",
            )

            with (
                patch.object(session_spine, "CLEAN", clean),
                patch.object(session_spine_validation, "CLEAN", clean),
                patch.object(session_spine_validation, "RAW", raw),
                patch.object(session_spine_validation, "BASE2", root),
                patch.object(session_spine_validation, "generate", return_value="# Session Spine Validation\n\n## Summary\n\nPass With Notes."),
            ):
                session_spine_validation.validate_session_spine("session02", model="test-model")

            report = (clean / "session02_spine_validation.md").read_text(encoding="utf-8")
            self.assertIn("# Session Spine Validation", report)
            self.assertIn("## Source Manifest", report)
            self.assertIn("session02_spine.yaml", report)
            self.assertIn("black candle lantern", report)


if __name__ == "__main__":
    unittest.main()
