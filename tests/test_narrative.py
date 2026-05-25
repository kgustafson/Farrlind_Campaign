import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import narrative


class NarrativeSummaryTest(unittest.TestCase):
    def test_generate_narrative_summary_uses_only_step_one_to_five_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            clean = root / "clean"
            sessions = root / "sessions"
            campaign_yaml = root / "campaign.yaml"
            raw.mkdir()
            clean.mkdir()
            sessions.mkdir()
            campaign_yaml.write_text("campaign:\n  name: Test Campaign\n", encoding="utf-8")
            (raw / "session02_transcript.txt").write_text(
                "The session begins on the road.\nThe party finds a green flame lantern.",
                encoding="utf-8",
            )
            (clean / "session02_curated.md").write_text("# Curated Session Packet\n\nLantern found.", encoding="utf-8")
            (clean / "session02_events.md").write_text("later event draft should not be read", encoding="utf-8")
            (sessions / "session02_context.yaml").write_text("title: Session 02\n", encoding="utf-8")

            with (
                patch.object(narrative, "RAW", raw),
                patch.object(narrative, "CLEAN", clean),
                patch.object(narrative, "SESSIONS", sessions),
                patch.object(narrative, "BASE2", root),
                patch.object(narrative, "campaign_metadata_path", return_value=campaign_yaml),
                patch.object(narrative, "campaign_glossary", return_value="- Campaign: Test Campaign."),
                patch.object(narrative, "generate", side_effect=[
                    "# Narrative Chunk Notes\n\n## Chronological Scenes\n\n- Road scene.",
                    "# Session Narrative Draft\n\nThe party finds a green flame lantern.",
                ]) as generate,
            ):
                narrative.generate_narrative_summary("session02", model="test-model")

            self.assertTrue((clean / "session02_narrative.md").exists())
            self.assertTrue((clean / "session02_narrative_chunks" / "chunk_001.md").exists())
            metadata = json.loads((clean / "session02_narrative_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["allowed_source_boundary"], "workflow_steps_1_through_5_only")
            self.assertIn("campaign.yaml", metadata["sources"])
            self.assertIn("raw/session02_transcript.txt", metadata["sources"])
            self.assertIn("clean/session02_curated.md", metadata["sources"])
            self.assertIn("sessions/session02_context.yaml", metadata["sources"])
            self.assertNotIn("clean/session02_events.md", metadata["sources"])

            synthesis_prompt = generate.call_args_list[-1].args[0]
            self.assertIn("STEP 5 CURATED PACKET", synthesis_prompt)
            self.assertIn("NARRATIVE CHUNK NOTES", synthesis_prompt)
            self.assertNotIn("later event draft should not be read", synthesis_prompt)

    def test_generate_narrative_summary_chunks_only_active_session_after_podcast_recap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            clean = root / "clean"
            sessions = root / "sessions"
            campaign_yaml = root / "campaign.yaml"
            raw.mkdir()
            clean.mkdir()
            sessions.mkdir()
            campaign_yaml.write_text("campaign:\n  name: Test Campaign\n", encoding="utf-8")
            (raw / "session02_transcript.txt").write_text(
                "Sponsor ad.\nQuick recap: the party fought dire wolves and solved a gate puzzle.\n"
                "That is where we are now. The party finds three corpses beside the road.",
                encoding="utf-8",
            )
            (clean / "session02_curated.md").write_text(
                "# Curated Session Packet\n\nThe recap mentions dire wolves. Active play has corpses.",
                encoding="utf-8",
            )

            with (
                patch.object(narrative, "RAW", raw),
                patch.object(narrative, "CLEAN", clean),
                patch.object(narrative, "SESSIONS", sessions),
                patch.object(narrative, "BASE2", root),
                patch.object(narrative, "campaign_metadata_path", return_value=campaign_yaml),
                patch.object(narrative, "campaign_glossary", return_value="- Campaign: Test Campaign."),
                patch.object(narrative, "generate", side_effect=[
                    "# Narrative Chunk Notes\n\n## Chronological Scenes\n\n- The party finds corpses.",
                    "# Session Narrative Draft\n\nThe party finds corpses.",
                ]) as generate,
            ):
                narrative.generate_narrative_summary("session02", model="test-model")

            chunk_prompt = generate.call_args_list[0].args[0]
            synthesis_prompt = generate.call_args_list[-1].args[0]
            metadata = json.loads((clean / "session02_narrative_metadata.json").read_text(encoding="utf-8"))
            self.assertNotIn("dire wolves and solved a gate puzzle", chunk_prompt)
            self.assertIn("The party finds three corpses", chunk_prompt)
            self.assertIn("PRIOR RECAP CONTEXT", synthesis_prompt)
            self.assertIn("recap-only material must not become", synthesis_prompt)
            self.assertEqual(metadata["active_session_boundary_marker"], "that is where we are now")

    def test_postprocess_removes_party_members_from_npc_section(self):
        text = """# Session Narrative Draft

## Key NPCs And Entities

- **Jens Lyndelle** - Retrieved weapons.
- **Bluetooth** - Onyx's familiar.
- **Ismark** - Kolyan's son.

## Character Notes

- **Jens Lyndelle** - Retrieved weapons.

## Party Interpretations Versus World Facts

- None identified.
"""
        metadata = {
            "party": [
                {"character_name": "Jens", "full_name": "Jens Lyndelle", "player_name": "Brian Murphy"}
            ],
            "glossary": [
                {"term": "Bluetooth", "note": "Onyx's imp familiar.", "aliases": ["Jens Z"]}
            ],
        }

        with patch("raglib.narrative.load_campaign_metadata", return_value=metadata):
            processed = narrative.postprocess_narrative(text)

        npc_section = processed.split("## Key NPCs And Entities", 1)[1].split("## Character Notes", 1)[0]
        self.assertNotIn("**Jens Lyndelle** - Retrieved weapons.", npc_section)
        self.assertNotIn("**Bluetooth** - Onyx's familiar.", npc_section)
        self.assertIn("**Ismark** - Kolyan's son.", processed)
        self.assertIn("## Character Notes", processed)

    def test_postprocess_relocates_party_interpretations_from_objective_sections(self):
        text = """# Session Narrative Draft

The party discusses the resort manager and Burger Master as if this is a customer-service dispute.

## Chronological Major Events

* The party discusses the goal of eliminating the Burger Master.
* The party reaches the village.

## Key Locations

- **Blood on the Vine** - The party believes it is a vegan restaurant on their meal plan.
- **Village of Barovia** - A frightened settlement.

## Party Interpretations Versus World Facts

- None identified.
"""

        with patch("raglib.narrative.load_campaign_metadata", return_value={}):
            processed = narrative.postprocess_narrative(text)

        intro = processed.split("## Chronological Major Events", 1)[0]
        chronology = processed.split("## Chronological Major Events", 1)[1].split("## Key Locations", 1)[0]
        locations = processed.split("## Key Locations", 1)[1].split("## Party Interpretations Versus World Facts", 1)[0]
        interpretations = processed.split("## Party Interpretations Versus World Facts", 1)[1]
        self.assertNotIn("Burger Master", intro)
        self.assertNotIn("Burger Master", chronology)
        self.assertIn("party reaches the village", chronology)
        self.assertNotIn("meal plan", locations)
        self.assertIn("Village of Barovia", locations)
        self.assertIn("Burger Master", interpretations)
        self.assertIn("meal plan", interpretations)

    def test_postprocess_preserves_objective_clause_from_mixed_npc_bullet(self):
        text = """# Session Narrative Draft

## Key NPCs And Entities

- **Strahd von Zarovich** - The Vampire lord of Barovia; the resort manager; the party's target.

## Party Interpretations Versus World Facts

- None identified.
"""

        with patch("raglib.narrative.load_campaign_metadata", return_value={}):
            processed = narrative.postprocess_narrative(text)

        npc_section = processed.split("## Key NPCs And Entities", 1)[1].split("## Party Interpretations Versus World Facts", 1)[0]
        interpretation_section = processed.split("## Party Interpretations Versus World Facts", 1)[1]
        self.assertIn("The Vampire lord of Barovia", npc_section)
        self.assertNotIn("resort manager", npc_section)
        self.assertIn("resort manager", interpretation_section)

    def test_postprocess_uses_latest_chunk_for_ending_location(self):
        text = """# Session Narrative Draft

## Timeline Seeds

- Starting location: Night Lotus.
- Ending location: Inside the tavern, Blood on the Vine.
- Real-world date: None identified.
"""
        chunk_outputs = [
            "## Timeline Seeds\n\n* Ending Location: Inside the tavern, Blood on the Vine.",
            "## Chronological Scenes\n\n* Ismark leads the party to the mansion doorway.\n* Ismark confronts them at the mansion door and Bluetooth attacks.",
        ]

        with patch("raglib.narrative.load_campaign_metadata", return_value={}):
            processed = narrative.postprocess_narrative(text, chunk_outputs)

        timeline = processed.split("## Timeline Seeds", 1)[1]
        self.assertIn("Ending location: Strahd von Zarovich's Mansion.", timeline)
        self.assertNotIn("Ending location: Inside the tavern", timeline)

    def test_postprocess_removes_recap_only_sentences(self):
        text = """# Session Narrative Draft

The party fought dire wolves at a gate. The party finds three corpses beside the road.

## Chronological Major Events

* The party encountered dire wolves at the gate.
* The party finds three corpses beside the road.

## Party Interpretations Versus World Facts

- None identified.
"""
        recap = "The party fought dire wolves at a gate."
        active = "That is where we are now. The party finds three corpses beside the road."

        with patch("raglib.narrative.load_campaign_metadata", return_value={}):
            processed = narrative.postprocess_narrative(text, active_transcript=active, recap_text=recap)

        self.assertNotIn("dire wolves", processed)
        self.assertIn("three corpses", processed)

    def test_postprocess_corrects_known_roles_and_companion_ownership(self):
        text = """# Session Narrative Draft

## Key NPCs And Entities

- **Kolyan Indirovich (Burgomaster)** - The vampire lord who sent the letter.
- **Ismark** - One of the party members who led them away.

## Character Notes

- **Jens Lyndelle (Bluetooth)** - Manifested the familiar Bluetooth; retrieved weapons.

## Needs Review

- None identified.
"""
        metadata = {
            "party": [{"character_name": "Jens", "full_name": "Jens Lyndelle"}],
            "glossary": [
                {"term": "Kolyan Indirovich", "note": "Burgomaster of Barovia.", "aliases": ["Kolyan"]},
                {"term": "Ismark", "note": "Kolyan's son.", "aliases": []},
                {"term": "Bluetooth", "note": "Onyx's imp familiar.", "aliases": ["Jens Z"]},
            ],
        }

        with patch("raglib.narrative.load_campaign_metadata", return_value=metadata):
            processed = narrative.postprocess_narrative(text)

        self.assertIn("**Kolyan Indirovich (Burgomaster)** - Burgomaster of Barovia.", processed)
        self.assertIn("**Ismark** - Kolyan's son.", processed)
        self.assertIn("**Jens Lyndelle** - retrieved weapons.", processed)
        character_notes = processed.split("## Character Notes", 1)[1].split("## Needs Review", 1)[0]
        self.assertNotIn("Manifested the familiar Bluetooth", character_notes)
        self.assertIn("Known role corrected for Kolyan", processed)
        self.assertIn("Companion ownership corrected", processed)

    def test_postprocess_flags_unsupported_found_location_claim(self):
        text = """# Session Narrative Draft

## Items Loot And Resources

- **Jar of Pickled Ghouls Tongues:** Found in the gift shop.

## Needs Review

- None identified.
"""
        active = "Nyack finds a jar of pickled ghouls tongues beside the corpses."

        with patch("raglib.narrative.load_campaign_metadata", return_value={}):
            processed = narrative.postprocess_narrative(text, active_transcript=active)

        self.assertIn("exact source/location needs review", processed)
        items_section = processed.split("## Items Loot And Resources", 1)[1].split("## Needs Review", 1)[0]
        self.assertNotIn("Found in the gift shop", items_section)
        self.assertIn("Unsupported found-location claim", processed)


if __name__ == "__main__":
    unittest.main()
