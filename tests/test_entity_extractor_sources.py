import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import (
    artifact_extractor,
    combat_encounter_extractor,
    location_extractor,
    lore_item_extractor,
    npc_extractor,
    open_thread_extractor,
)


class EntityExtractorSourceTest(unittest.TestCase):
    def test_auto_sources_include_spine_and_narrative_context(self):
        modules = [
            npc_extractor,
            location_extractor,
            artifact_extractor,
            lore_item_extractor,
            combat_encounter_extractor,
            open_thread_extractor,
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "knowledge" / "Faban"
            clean = base / "clean"
            raw = base / "raw"
            final = base / "final"
            for path in [clean, raw, final]:
                path.mkdir(parents=True)
            (clean / "session21_spine.yaml").write_text("major_events: []", encoding="utf-8")
            (clean / "session21_narrative.md").write_text("narrative", encoding="utf-8")
            (clean / "session21_curated.md").write_text("curated", encoding="utf-8")
            (clean / "session21_summary.md").write_text("model summary", encoding="utf-8")
            (clean / "session21_diary.md").write_text("diary", encoding="utf-8")
            (raw / "session21_transcript.txt").write_text("transcript", encoding="utf-8")

            for module in modules:
                with self.subTest(module=module.__name__), \
                     patch.object(module, "BASE", base), \
                     patch.object(module, "CLEAN", clean), \
                     patch.object(module, "RAW", raw):
                    sources = module.load_session_sources("session21")

                self.assertEqual(
                    [source["label"] for source in sources],
                    ["session_spine", "narrative", "curated_packet", "draft_summary", "diary"],
                )


if __name__ == "__main__":
    unittest.main()
