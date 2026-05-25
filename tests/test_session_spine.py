import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from raglib import session_spine


class SessionSpineTest(unittest.TestCase):
    def test_extract_yaml_document_accepts_fenced_yaml(self):
        document = session_spine.extract_yaml_document("""```yaml
session: session02
major_events:
  - title: Road
    summary: Travel begins.
```""")

        self.assertEqual(document["session"], "session02")
        self.assertEqual(document["major_events"][0]["title"], "Road")

    def test_extract_yaml_document_repairs_plain_scalar_colons(self):
        document = session_spine.extract_yaml_document("""session: session02
major_events:
  - order: 1
    title: Misread Goal
    summary: The party discussed their goal: complain to the manager.
    outcome: The bit continued.
""")

        self.assertEqual(
            document["major_events"][0]["summary"],
            "The party discussed their goal: complain to the manager.",
        )

    def test_extract_session_spine_writes_normalized_yaml(self):
        output = """session: session02
timeline:
  starting_location: Night Lotus
  ending_location: Mansion doorway
major_events:
  - order: 2
    title: Zombies Rise
    event_type: combat
    location: Woods
    summary: Three corpses rise as zombies.
    party_members: [Jens, Nyack]
    npcs: []
    entities: [Zombies]
    items: [Envelope]
    party_interpretation: ""
    outcome: Party escapes.
    evidence: Narrative combat section.
    needs_review: []
  - order: 1
    title: Svalich Road
    summary: The party travels through Barovia.
open_threads:
  - Ismark confrontation unresolved.
needs_review: []
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            clean.mkdir()
            (clean / "session02_narrative.md").write_text("# Session Narrative Draft\n\nRoad then zombies.", encoding="utf-8")

            with (
                patch.object(session_spine, "CLEAN", clean),
                patch.object(session_spine, "BASE2", root),
                patch.object(session_spine, "generate", return_value=output),
            ):
                session_spine.extract_session_spine("session02", model="test-model")

            spine = yaml.safe_load((clean / "session02_spine.yaml").read_text(encoding="utf-8"))
            self.assertEqual(spine["source"], "clean/session02_narrative.md")
            self.assertEqual([event["order"] for event in spine["major_events"]], [1, 2])
            self.assertEqual(spine["timeline"]["real_world_date"], "N/A")
            self.assertEqual(spine["major_events"][0]["title"], "Svalich Road")
            self.assertTrue((clean / "session02_spine_metadata.yaml").exists())

    def test_normalize_spine_removes_npc_from_named_location_context(self):
        document = {
            "session": "session02",
            "timeline": {},
            "major_events": [{
                "order": 1,
                "title": "Approach to Mansion",
                "event_type": "travel",
                "location": "Strahd von Zarovich's Mansion",
                "summary": "The party approaches Strahd von Zarovich's mansion behind a rusting iron fence.",
                "npcs": ["Strahd von Zarovich"],
            }, {
                "order": 2,
                "title": "Ismark Confronts The Party",
                "event_type": "social",
                "location": "Strahd von Zarovich's Mansion",
                "summary": "Ismark draws a knife and confronts the party.",
                "npcs": ["Ismark"],
            }],
        }
        metadata = {
            "glossary": [
                {"term": "Strahd von Zarovich", "note": "Vampire lord of Barovia."},
                {"term": "Ismark", "note": "Kolyan's son."},
            ]
        }

        with (
            patch.object(session_spine, "BASE2", Path("/tmp")),
            patch("raglib.session_spine.load_campaign_metadata", return_value=metadata),
        ):
            spine = session_spine.normalize_spine(document, "session02")

        self.assertEqual(spine["major_events"][0]["npcs"], [])
        self.assertIn("contextual", spine["major_events"][0]["needs_review"][0])
        self.assertEqual(spine["major_events"][1]["npcs"], ["Ismark"])

    def test_normalize_spine_preserves_missing_items_and_cliffhanger_from_narrative(self):
        document = {
            "session": "session02",
            "timeline": {"ending_location": "Mansion"},
            "major_events": [{
                "order": 1,
                "title": "Zombie Combat",
                "event_type": "combat",
                "location": "Woods",
                "summary": "The party fights zombies.",
                "items": ["Envelope"],
                "needs_review": [],
            }],
        }
        narrative = """# Session Narrative Draft

## Combat And Encounters

- **Final Confrontation:** Ismark confronts the party and Bluetooth attacks as the session ends mid-attack.

## Items Loot And Resources

- **Rusty Short Swords** - Found clutched by a corpse.
- **Lantern** found; exact source/location needs review.

## Character Notes

- **Nyack of the Ran'afor** - Used Hunter's Mark and Zephyr Strike to escape.

## Open Threads

- The immediate outcome of the confrontation with Ismark and Bluetooth is unresolved, as the session ended mid-attack.
"""

        with patch.object(session_spine, "BASE2", Path("/tmp")), patch("raglib.session_spine.load_campaign_metadata", return_value={}):
            spine = session_spine.normalize_spine(document, "session02", narrative)

        event = spine["major_events"][0]
        self.assertIn("Rusty Short Swords", event["items"])
        self.assertIn("Lantern", event["items"])
        self.assertTrue(any("Preserved narrative item" in note for note in event["needs_review"]))
        self.assertIn("Nyack of the Ran'afor", event["party_members"])
        self.assertTrue(any("Hunter's Mark" in note for note in event["needs_review"]))
        self.assertEqual(spine["major_events"][1]["event_type"], "cliffhanger")
        self.assertIn("Bluetooth", spine["major_events"][1]["summary"])


if __name__ == "__main__":
    unittest.main()
