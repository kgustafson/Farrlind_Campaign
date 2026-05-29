import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import extract


class ExtractSessionTest(unittest.TestCase):
    def test_event_source_packet_prefers_clean_narrative_and_spine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            clean = root / "clean"
            raw.mkdir()
            clean.mkdir()
            (raw / "session02_transcript.txt").write_text("raw transcript", encoding="utf-8")
            (clean / "session02_curated.md").write_text("curated fallback", encoding="utf-8")
            (clean / "session02_narrative.md").write_text("clean narrative", encoding="utf-8")
            (clean / "session02_spine.yaml").write_text("spine yaml", encoding="utf-8")
            (clean / "session02_spine_validation.md").write_text("validation report", encoding="utf-8")

            with patch.object(extract, "RAW", raw), patch.object(extract, "CLEAN", clean):
                packet, source_kind = extract.event_source_packet("session02")

        self.assertEqual(source_kind, "clean narrative and spine packet")
        self.assertIn("SESSION SPINE", packet)
        self.assertIn("spine yaml", packet)
        self.assertIn("STEP 6 CLEAN NARRATIVE", packet)
        self.assertIn("clean narrative", packet)
        self.assertNotIn("curated fallback", packet)
        self.assertNotIn("validation report", packet)
        self.assertNotEqual(packet, "curated fallback")

    def test_extract_session_writes_events_from_clean_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            raw = root / "raw"
            clean.mkdir()
            raw.mkdir()
            (clean / "session02_narrative.md").write_text("""# Session Narrative Draft

## Chronological Major Events

- The party finds a lantern.
- Ismark confronts the party and Bluetooth attacks.
""", encoding="utf-8")
            (clean / "session02_spine.yaml").write_text("""major_events:
  - title: Lantern Discovery
    event_type: discovery
    location: Road
    summary: The party finds a lantern.
    items: [Lantern]
    outcome: Lantern acquired.
  - title: Final Confrontation
    event_type: cliffhanger
    location: Mansion
    summary: Ismark confronts the party and Bluetooth attacks.
    npcs: [Ismark]
    entities: [Bluetooth]
    outcome: Session ends mid-attack.
""", encoding="utf-8")

            with (
                patch.object(extract, "RAW", raw),
                patch.object(extract, "CLEAN", clean),
                patch.object(extract, "chat") as chat,
            ):
                extract.extract_session("session02")

            output = (clean / "session02_events.md").read_text(encoding="utf-8")
            chat.assert_not_called()
            self.assertIn("EVENT:", output)
            self.assertIn("The party finds a lantern.", output)
            self.assertIn("event_type: social", output)
            self.assertIn("spine_type=cliffhanger", output)
            self.assertIn("targets: Bluetooth", output)

    def test_deterministic_clean_events_appends_unrepresented_spine_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean"
            raw = root / "raw"
            clean.mkdir()
            raw.mkdir()
            (clean / "session02_narrative.md").write_text("""# Session Narrative Draft

## Chronological Major Events

- The party finds a lantern.
""", encoding="utf-8")
            (clean / "session02_spine.yaml").write_text("""major_events:
  - order: 1
    title: Lantern Discovery
    event_type: discovery
    location: Road
    summary: The party finds a lantern.
    items: [Lantern]
    outcome: Lantern acquired.
  - order: 2
    title: Final Confrontation
    event_type: cliffhanger
    location: Mansion
    summary: Ismark confronts the party and Bluetooth attacks.
    npcs: [Ismark]
    entities: [Bluetooth]
    outcome: Session ends mid-attack.
""", encoding="utf-8")

            with patch.object(extract, "RAW", raw), patch.object(extract, "CLEAN", clean):
                output = extract.deterministic_clean_events("session02")

        self.assertIn("The party finds a lantern.", output)
        self.assertIn("Ismark confronts the party and Bluetooth attacks.", output)
        self.assertIn("event_type: social", output)
        self.assertIn("spine_type=cliffhanger", output)


if __name__ == "__main__":
    unittest.main()
