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

    def test_load_session_sources_includes_model_summary_with_curated_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "knowledge" / "Faban"
            clean = base / "clean"
            raw = base / "raw"
            final = base / "final"
            for path in [clean, raw, final]:
                path.mkdir(parents=True)
            (clean / "session21_curated.md").write_text("curated", encoding="utf-8")
            (clean / "session21_summary.md").write_text("model summary", encoding="utf-8")
            (clean / "session21_diary.md").write_text("diary", encoding="utf-8")
            (raw / "session21_transcript.txt").write_text("transcript", encoding="utf-8")

            with patch.object(npc_extractor, "BASE", base), \
                 patch.object(npc_extractor, "CLEAN", clean), \
                 patch.object(npc_extractor, "RAW", raw):
                sources = npc_extractor.load_session_sources("session21")

        self.assertEqual([source["label"] for source in sources], ["curated_packet", "draft_summary", "diary"])
        self.assertEqual([source["text"] for source in sources], ["curated", "model summary", "diary"])

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

    def test_postprocess_rejects_party_misunderstanding_as_npc(self):
        document = {
            "known_npc_mentions": [],
            "new_npc_candidates": [{
                "proposed_name": "Burger Master",
                "role": "Manager of a restaurant empire",
                "description": "The party mistakenly interprets the Burgomaster title as a burger boss.",
                "evidence": "The party misreads Burgomaster as Burger Master.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            [],
            {"party": []},
            "session02",
            "Because of the title Burgomaster, the party misreads it as Burger Master and jokes about a secret recipe.",
        )

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Burger Master")
        self.assertIn("party-interpretation NPC", warnings[0])

    def test_postprocess_neutralizes_party_interpretation_known_update(self):
        registry = [{"id": 4, "name": "Strahd von Zarovich", "alias": "Strahd"}]
        document = {
            "known_npc_mentions": [{
                "npc_id": 4,
                "canonical_name": "Strahd von Zarovich",
                "mentioned_as": ["Strahd"],
                "new_information": "The party mistakenly calls Strahd the resort manager.",
                "evidence": "The Triplets keep interpreting Strahd as the manager.",
            }],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": []},
            "session02",
            "The Triplets keep interpreting Strahd as the manager, but Kolyan's letter frames him as a vampire threat.",
        )

        self.assertEqual(
            cleaned["known_npc_mentions"][0]["new_information"],
            "Mentioned in this session; no new canon update proposed.",
        )
        self.assertIn("Neutralized party-interpretation NPC update", warnings[0])

    def test_postprocess_neutralizes_existing_npc_candidate_with_party_framed_role(self):
        registry = [{"id": 4, "name": "Strahd von Zarovich", "alias": "Strahd"}]
        document = {
            "known_npc_mentions": [],
            "new_npc_candidates": [{
                "proposed_name": "Strahd",
                "npc_kind": "named_individual",
                "role": "Manager of the establishment",
                "description": "The manager the party wants to complain to.",
                "first_seen_session": 2,
                "confidence": "high",
                "evidence": "I have a bone to pick with the manager, Strahd.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": []},
            "session02",
            "I have a bone to pick with the manager, Strahd. Kolyan's letter describes Strahd as a vampire threat.",
        )

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["known_npc_mentions"][0]["canonical_name"], "Strahd von Zarovich")
        self.assertEqual(
            cleaned["known_npc_mentions"][0]["new_information"],
            "Mentioned in this session; no new canon update proposed.",
        )
        self.assertIn("Neutralized party-framed NPC candidate update", warnings[0])

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

    def test_postprocess_allows_repeated_name_drift(self):
        registry = [{"id": 4, "name": "Strahd Von Zorovich", "alias": "Strahd"}]
        document = {
            "known_npc_mentions": [{
                "npc_id": 4,
                "canonical_name": "Strahd von Zarovich von Zarovich",
                "mentioned_as": ["Strahd"],
            }],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, _warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {"party": []},
            "session02",
            "Strahd von Zarovich is named in Kolyan's letter.",
        )

        self.assertEqual(cleaned["known_npc_mentions"][0]["canonical_name"], "Strahd Von Zorovich")

    def test_postprocess_recovers_unknown_glossary_known_mention_as_new_candidate(self):
        document = {
            "known_npc_mentions": [{
                "npc_id": 99,
                "canonical_name": "Marina Kulyana Kulyana",
                "mentioned_as": ["Marina"],
                "new_information": "Kolyan's adopted daughter has been bitten by a vampire.",
                "location": "Barovia",
                "confidence": "high",
                "evidence": "My adopted daughter, the fair Marina Kuljana...",
            }],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            [],
            {
                "party": [],
                "glossary": [{
                    "term": "Marina Kulyana",
                    "note": "Kolyan's adopted daughter, bitten by a vampire.",
                    "aliases": ["Marina", "Marina Kuljana"],
                }],
            },
            "session02",
            "My adopted daughter, the fair Marina Kuljana, languishes and dies.",
        )

        self.assertEqual(cleaned["known_npc_mentions"], [])
        self.assertEqual(cleaned["new_npc_candidates"][0]["proposed_name"], "Marina Kulyana")
        self.assertIn("Recovered unknown-id known mention", warnings[0])

    def test_postprocess_recovers_mismatched_glossary_known_mention_as_new_candidate(self):
        registry = [{"id": 2, "name": "Reagan", "alias": ""}]
        document = {
            "known_npc_mentions": [{
                "npc_id": 2,
                "canonical_name": "Bluetooth",
                "mentioned_as": ["Bluetooth"],
                "new_information": "Onyx's imp familiar.",
                "confidence": "high",
                "evidence": "Everyone, meet Bluetooth.",
            }],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            registry,
            {
                "party": [],
                "glossary": [{
                    "term": "Bluetooth",
                    "note": "Onyx's imp familiar.",
                    "aliases": ["Jens Z"],
                }],
            },
            "session02",
            "Everyone, meet Bluetooth.",
        )

        self.assertEqual(cleaned["known_npc_mentions"], [])
        self.assertEqual(cleaned["new_npc_candidates"][0]["proposed_name"], "Bluetooth")
        self.assertIn("Recovered mismatched-id known mention", warnings[0])

    def test_postprocess_keeps_explicit_npc_despite_party_framing_nearby(self):
        document = {
            "known_npc_mentions": [{
                "npc_id": 2,
                "canonical_name": "Doru",
                "mentioned_as": ["Doru"],
                "new_information": "Doru is trapped behind a trap door.",
                "confidence": "high",
                "evidence": "I am Doru.",
            }],
            "new_npc_candidates": [{
                "proposed_name": "Doru",
                "npc_kind": "named_individual",
                "role": "Father Donovich's brother.",
                "description": "A captive brother of the priest trapped behind a trap door.",
                "first_seen_session": 3,
                "first_seen_location": "Church",
                "aliases": [],
                "status": "unknown",
                "confidence": "high",
                "evidence": "I am Doru.",
            }],
            "rejected_candidates": [{"text": "Doru", "reason": "party interpretation"}],
            "uncertainties": [],
        }

        cleaned, _warnings = npc_extractor.postprocess_extraction(
            document,
            [{"id": 2, "name": "Dolphin", "alias": ""}],
            {"party": []},
            "session03",
            "- **Doru** - A captive brother of the priest, trapped behind a trap door.\n"
            "The party plans what to do about the fate of Doru.",
        )

        self.assertEqual(cleaned["new_npc_candidates"][0]["proposed_name"], "Doru")
        self.assertEqual(cleaned["rejected_candidates"], [])

    def test_postprocess_adds_glossary_names_found_in_source(self):
        cleaned, _warnings = npc_extractor.postprocess_extraction(
            {
                "known_npc_mentions": [],
                "new_npc_candidates": [],
                "rejected_candidates": [],
                "uncertainties": [],
            },
            [],
            {
                "party": [{"character_name": "Onyx"}],
                "glossary": [
                    {"term": "Ismark", "note": "Kolyan's son.", "aliases": ["Ismark the Lesser"]},
                    {"term": "Onyx", "note": "Party member.", "aliases": []},
                ],
            },
            "session02",
            "Ismark leads you out of the tavern.",
        )

        self.assertEqual([item["proposed_name"] for item in cleaned["new_npc_candidates"]], ["Ismark"])

    def test_postprocess_does_not_add_location_glossary_names_as_npcs(self):
        cleaned, _warnings = npc_extractor.postprocess_extraction(
            {
                "known_npc_mentions": [],
                "new_npc_candidates": [],
                "rejected_candidates": [],
                "uncertainties": [],
            },
            [],
            {
                "party": [],
                "glossary": [{
                    "term": "Barovia",
                    "note": "Gothic domain where the Triplets are trapped.",
                    "aliases": ["Borovia"],
                }],
            },
            "session02",
            "The party enters Barovia.",
        )

        self.assertEqual(cleaned["new_npc_candidates"], [])

    def test_postprocess_rejects_burger_master_variants(self):
        cleaned, warnings = npc_extractor.postprocess_extraction(
            {
                "known_npc_mentions": [],
                "new_npc_candidates": [{
                    "proposed_name": "Burger Master's Daughter",
                    "role": "Daughter of the burger master",
                    "description": "The party thinks the Burgomaster is a burger master.",
                    "evidence": "The party jokes about the Burger Master and his daughter.",
                }],
                "rejected_candidates": [],
                "uncertainties": [],
            },
            [],
            {"party": []},
            "session02",
            "The party jokes about the Burger Master and his daughter.",
        )

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Burger Master's Daughter")
        self.assertIn("Burger Master", warnings[0])

    def test_postprocess_dedupes_candidates_and_removes_matching_rejections(self):
        cleaned, _warnings = npc_extractor.postprocess_extraction(
            {
                "known_npc_mentions": [],
                "new_npc_candidates": [
                    {"proposed_name": "Dolphin", "evidence": "Dolphin speaks."},
                    {"proposed_name": "Dolphin", "evidence": "Dolphin is recognized."},
                ],
                "rejected_candidates": [{"text": "Dolphin", "reason": "Earlier bad model pass."}],
                "uncertainties": [],
            },
            [],
            {"party": []},
            "session02",
            "Dolphin speaks.",
        )

        self.assertEqual([item["proposed_name"] for item in cleaned["new_npc_candidates"]], ["Dolphin"])
        self.assertEqual(cleaned["rejected_candidates"], [])

    def test_postprocess_treats_regan_as_reagan(self):
        cleaned, _warnings = npc_extractor.postprocess_extraction(
            {
                "known_npc_mentions": [],
                "new_npc_candidates": [{"proposed_name": "Regan", "evidence": "Regan appears."}],
                "rejected_candidates": [],
                "uncertainties": [],
            },
            [{"id": 2, "name": "Reagan", "alias": ""}],
            {"party": []},
            "session02",
            "Regan appears.",
        )

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["known_npc_mentions"][0]["canonical_name"], "Reagan")

    def test_postprocess_rejects_known_mapping_when_only_generic_role_is_in_source(self):
        cleaned, warnings = npc_extractor.postprocess_extraction(
            {
                "known_npc_mentions": [{
                    "npc_id": 2,
                    "canonical_name": "Reagan",
                    "mentioned_as": ["bartender"],
                    "evidence": "The bartender, Dolphin, recognized one of the party members.",
                }],
                "new_npc_candidates": [],
                "rejected_candidates": [],
                "uncertainties": [],
            },
            [{"id": 2, "name": "Reagan", "alias": ""}],
            {"party": []},
            "session02",
            "The bartender, Dolphin, recognized one of the party members.",
        )

        self.assertEqual(cleaned["known_npc_mentions"], [])
        self.assertIn("not present in session source", warnings[0])

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

    def test_postprocess_rejects_new_candidate_absent_from_source(self):
        document = {
            "known_npc_mentions": [],
            "new_npc_candidates": [{
                "proposed_name": "Uthgar",
                "role": "Smith contact in Catur",
                "description": "A copied example candidate.",
            }],
            "rejected_candidates": [],
            "uncertainties": [],
        }

        cleaned, warnings = npc_extractor.postprocess_extraction(
            document,
            [],
            {"party": []},
            "session01",
            "Keychain led the party toward the Overseer's Manor.",
        )

        self.assertEqual(cleaned["new_npc_candidates"], [])
        self.assertEqual(cleaned["rejected_candidates"][0]["text"], "Uthgar")
        self.assertIn("not present in source", warnings[0])

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

    def test_extract_npcs_chunks_large_transcript_source(self):
        output = {
            "known_npc_mentions": [],
            "new_npc_candidates": [],
            "rejected_candidates": [],
            "uncertainties": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "knowledge" / "Faban"
            clean = base / "clean"
            raw = base / "raw"
            for path in [clean, raw]:
                path.mkdir(parents=True)
            long_text = "\n".join(f"[00:{index:02d}:00] No NPC here." for index in range(2500))
            (raw / "session21_transcript.txt").write_text(long_text, encoding="utf-8")

            with patch.object(npc_extractor, "BASE", base), \
                 patch.object(npc_extractor, "CLEAN", clean), \
                 patch.object(npc_extractor, "RAW", raw), \
                 patch.object(npc_extractor, "OUTPUT_DIR", base / "extracted"), \
                 patch.object(npc_extractor, "load_campaign_metadata", return_value={"party": []}), \
                 patch.object(npc_extractor, "npc_registry", return_value=[]), \
                 patch("raglib.npc_extractor.canon.locations", return_value=[]), \
                 patch("raglib.npc_extractor.generate", return_value=json.dumps(output)) as generate:
                path = npc_extractor.extract_npcs("session21", model="test-model", source="transcript")

            metadata = json.loads(path.with_name("session21_npcs_metadata.json").read_text(encoding="utf-8"))

        self.assertGreater(generate.call_count, 1)
        self.assertTrue(metadata["chunked"])
        self.assertEqual(metadata["chunk_count"], generate.call_count)


if __name__ == "__main__":
    unittest.main()
