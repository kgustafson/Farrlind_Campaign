import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import npc_extractor


class NpcExtractorTest(unittest.TestCase):
    def test_load_session_sources_prefers_final_summary_and_diary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "knowledge" / "Faban"
            clean = base / "clean"
            raw = base / "raw"
            final = base / "final"
            for path in [clean, raw, final]:
                path.mkdir(parents=True)
            (final / "session21_summary.md").write_text("final", encoding="utf-8")
            (clean / "session21_curated.md").write_text("curated", encoding="utf-8")
            (clean / "session21_diary.md").write_text("diary", encoding="utf-8")
            (raw / "session21_transcript.txt").write_text("transcript", encoding="utf-8")

            with patch.object(npc_extractor, "BASE", base), \
                 patch.object(npc_extractor, "CLEAN", clean), \
                 patch.object(npc_extractor, "RAW", raw):
                sources = npc_extractor.load_session_sources("session21")

        self.assertEqual([source["label"] for source in sources], ["final_summary", "diary"])
        self.assertEqual([source["text"] for source in sources], ["final", "diary"])

    def test_extract_json_object_accepts_markdown_wrapped_json(self):
        document = npc_extractor.extract_json_object("""```json
{
  "known_npc_mentions": [],
  "new_npc_candidates": [{"proposed_name": "Uthgar"}],
  "rejected_candidates": [],
  "uncertainties": []
}
```""")

        self.assertEqual(document["new_npc_candidates"][0]["proposed_name"], "Uthgar")

    def test_load_campaign_metadata_returns_party_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "knowledge" / "Faban"
            base.mkdir(parents=True)
            (base / "campaign.yaml").write_text("""
party:
  - character_name: Faban
    full_name: Faban Colon
    player_name: Kurt Gustafson
  - character_name: Corvinas
    player_name: Chris Ward
    aliases:
      - Corvinus
""", encoding="utf-8")

            with patch.object(npc_extractor, "BASE", base):
                metadata = npc_extractor.load_campaign_metadata()

        self.assertEqual(
            npc_extractor.party_character_names(metadata),
            ["Corvinas", "Corvinus", "Faban", "Faban Colon"],
        )

    def test_normalize_extraction_keeps_exact_top_level_shape(self):
        normalized = npc_extractor.normalize_extraction({
            "known_npc_mentions": [{"npc_id": 1}],
            "new_npc_candidates": "bad",
            "extra": [{"ignored": True}],
        })

        self.assertEqual(list(normalized.keys()), [
            "known_npc_mentions",
            "new_npc_candidates",
            "rejected_candidates",
            "uncertainties",
        ])
        self.assertEqual(normalized["known_npc_mentions"], [{"npc_id": 1}])
        self.assertEqual(normalized["new_npc_candidates"], [])

    def test_postprocess_drops_party_mentions_and_bad_npc_id_matches(self):
        registry = [
            {"id": 1, "name": "Jennifer", "alias": ""},
            {"id": 23, "name": "Lightdelver", "alias": ""},
        ]
        document = {
            "known_npc_mentions": [
                {"npc_id": 1, "canonical_name": "Jennifer", "mentioned_as": ["Mikani"]},
                {"npc_id": 1, "canonical_name": "Gildas", "mentioned_as": ["Gildas"]},
                {"npc_id": 23, "canonical_name": "Lightdelver", "mentioned_as": ["Lightdelver"]},
            ],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": [{"character_name": "Mikani"}, {"character_name": "Gildas"}]},
            "session19",
            "Lightdelver helped in Balrog.",
        )

        self.assertEqual([item["canonical_name"] for item in cleaned["known_npc_mentions"]], ["Lightdelver"])
        self.assertEqual(len(warnings), 2)

    def test_postprocess_drops_known_mentions_absent_from_source(self):
        registry = [
            {"id": 27, "name": "Alistair", "alias": "Allister"},
            {"id": 23, "name": "Lightdelver", "alias": ""},
        ]
        document = {
            "known_npc_mentions": [
                {"npc_id": 27, "canonical_name": "Alistair", "mentioned_as": ["Alistair"]},
                {"npc_id": 23, "canonical_name": "Lightdelver", "mentioned_as": ["Lightdelver"]},
            ],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": []},
            "session19",
            "Lightdelver joined the fight.",
        )

        self.assertEqual([item["canonical_name"] for item in cleaned["known_npc_mentions"]], ["Lightdelver"])
        self.assertIn("not present in session source", warnings[0])

    def test_postprocess_corrects_alias_canonical_name(self):
        registry = [{"id": 27, "name": "Alistair", "alias": "Allister"}]
        document = {
            "known_npc_mentions": [{"npc_id": 27, "canonical_name": "Allister", "mentioned_as": ["Allister"]}],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, _warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": []},
            "session21",
            "Allister warned Faban.",
        )

        self.assertEqual(cleaned["known_npc_mentions"][0]["canonical_name"], "Alistair")

    def test_postprocess_allows_combined_name_alias_canonical(self):
        registry = [{"id": 43, "name": "Niebain", "alias": "Nebain"}]
        document = {
            "known_npc_mentions": [{"npc_id": 43, "canonical_name": "Niebain / Nebain", "mentioned_as": ["Niebain"]}],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, _warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": []},
            "session21",
            "It named itself Niebain or Nebain.",
        )

        self.assertEqual(cleaned["known_npc_mentions"][0]["canonical_name"], "Niebain")

    def test_postprocess_moves_existing_candidate_to_known_mentions(self):
        registry = [{"id": 26, "name": "Orsydon", "alias": ""}]
        document = {
            "known_npc_mentions": [],
            "new_npc_candidates": [{
                "proposed_name": "Orsydon",
                "role": "Dragon",
                "description": "The dragon summoned in Balrog.",
                "first_seen_location": "Balrog",
                "confidence": "high",
                "evidence": "Cultists summoned the dragon Orsydon.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": []},
            "session19",
            "Cultists summoned the dragon Orsydon.",
        )

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["known_npc_mentions"][0]["npc_id"], 26)
        self.assertIn("Moved existing NPC candidate", warnings[0])

    def test_postprocess_rejects_duplicate_existing_candidate(self):
        registry = [{"id": 41, "name": "Uthgar", "alias": ""}]
        document = {
            "known_npc_mentions": [{"npc_id": 41, "canonical_name": "Uthgar", "mentioned_as": ["Uthgar"]}],
            "new_npc_candidates": [{"proposed_name": "Uthgar", "role": "Smith"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(document, registry, {"party": []}, "session21")

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Uthgar")
        self.assertIn("duplicate", warnings[0])

    def test_postprocess_rejects_fisherman_representative_when_group_exists(self):
        registry = [{"id": 40, "name": "Giant fishermen", "alias": ""}]
        document = {
            "known_npc_mentions": [{"npc_id": 40, "canonical_name": "Giant fishermen", "mentioned_as": ["fishermen"]}],
            "new_npc_candidates": [{"proposed_name": "Sun-worn Fisherman", "role": "Representative of the Giant fishermen"}],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(document, registry, {"party": []}, "session20")

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["reason"], "Representative of existing Giant fishermen group.")
        self.assertIn("representative group", warnings[0])

    def test_extract_npcs_writes_review_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "knowledge" / "Faban"
            clean = base / "clean"
            final = base / "final"
            raw = base / "raw"
            for path in [clean, final, raw]:
                path.mkdir(parents=True)
            (final / "session21_summary.md").write_text("The party met Uthgar.", encoding="utf-8")
            output = {
                "known_npc_mentions": [],
                "new_npc_candidates": [{
                    "proposed_name": "Uthgar",
                    "npc_kind": "named_individual",
                    "role": "Smith contact in Catur",
                    "description": "A smith in Catur.",
                    "first_seen_session": 21,
                    "first_seen_location": "Catur",
                    "aliases": [],
                    "status": "unknown",
                    "confidence": "high",
                    "evidence": "The party met Uthgar.",
                }],
                "rejected_candidates": [],
                "uncertainties": [],
            }

            with patch.object(npc_extractor, "BASE", base), \
                 patch.object(npc_extractor, "CLEAN", clean), \
                 patch.object(npc_extractor, "RAW", raw), \
                 patch.object(npc_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(npc_extractor, "load_campaign_metadata", return_value={"party": [{"character_name": "Faban"}]}), \
                 patch.object(npc_extractor, "npc_registry", return_value=[{"id": 1, "name": "Allister"}]), \
                 patch("raglib.npc_extractor.canon.locations", return_value=["Catur"]), \
                 patch("raglib.npc_extractor.generate", return_value=json.dumps(output)):
                path = npc_extractor.extract_npcs("session21", model="test-model")

            written = json.loads(path.read_text(encoding="utf-8"))
            metadata = json.loads(path.with_name("session21_npcs_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(written, output)
        self.assertEqual(metadata["guardrail_warning_count"], 0)


if __name__ == "__main__":
    unittest.main()
