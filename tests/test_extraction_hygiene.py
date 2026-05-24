import unittest

from raglib.extraction_hygiene import (
    compact_campaign_metadata,
    compact_name_list_for_chunk,
    compact_registry_for_chunk,
)


class ExtractionHygieneTest(unittest.TestCase):
    def test_compact_registry_for_chunk_matches_aliases_and_keeps_only_requested_fields(self):
        registry = [
            {
                "id": 1,
                "name": "Strahd von Zarovich",
                "alias": "Strahd; The Manager",
                "notes": "Large canon note that should not be sent per chunk.",
            },
            {
                "id": 2,
                "name": "Kolyan Indirovich",
                "alias": "",
                "notes": "Not mentioned here.",
            },
        ]

        compacted = compact_registry_for_chunk(
            "The party asks whether Strahd is the manager of Barovia.",
            registry,
            identity_fields=["name", "alias"],
            keep_fields=["id", "name", "alias"],
        )

        self.assertEqual(compacted, [{
            "id": 1,
            "name": "Strahd von Zarovich",
            "alias": "Strahd; The Manager",
        }])

    def test_compact_registry_for_chunk_matches_list_aliases_without_ids(self):
        registry = [
            {"title": "Bluetooth", "aliases": ["Jens Z", "Jens Z. Bluetooth"], "description": "Long text."},
            {"title": "Black Candle Lantern", "aliases": [], "description": "Not in this chunk."},
        ]

        compacted = compact_registry_for_chunk(
            "Onyx orders Jens Z. Bluetooth to attack.",
            registry,
            identity_fields=["title", "aliases"],
            keep_fields=["title", "aliases"],
        )

        self.assertEqual(compacted, [{"title": "Bluetooth", "aliases": ["Jens Z", "Jens Z. Bluetooth"]}])

    def test_compact_name_list_for_chunk_keeps_only_mentioned_names(self):
        compacted = compact_name_list_for_chunk(
            "They travel down the muddy Svalich road into fog.",
            ["Village of Barovia", "Svalich Road", "Blood on the Vine"],
        )

        self.assertEqual(compacted, ["Svalich Road"])

    def test_compact_campaign_metadata_keeps_identity_context(self):
        metadata = {
            "campaign": {"id": "trinyvale", "name": "Trinyvale X Strahd", "private_notes": "omit"},
            "dm": {"name": "Caldwell Tanner", "aliases": ["Caldwell"], "email": "omit"},
            "party": [{
                "character_name": "Onyx",
                "full_name": "Onyx Lumiere",
                "player_name": "Emily Axford",
                "notes": "omit",
            }],
            "glossary": [{"term": "Barovia", "aliases": ["Borovia"], "note": "omit"}],
            "extraction_guidance": {"players_are_not_campaign_npcs": True},
        }

        compacted = compact_campaign_metadata(metadata)

        self.assertEqual(compacted["campaign"], {"id": "trinyvale", "name": "Trinyvale X Strahd"})
        self.assertEqual(compacted["dm"], {"name": "Caldwell Tanner", "aliases": ["Caldwell"]})
        self.assertEqual(compacted["party"], [{
            "character_name": "Onyx",
            "full_name": "Onyx Lumiere",
            "player_name": "Emily Axford",
        }])
        self.assertEqual(compacted["glossary"], [{"term": "Barovia", "aliases": ["Borovia"]}])
        self.assertEqual(compacted["extraction_guidance"], {"players_are_not_campaign_npcs": True})


if __name__ == "__main__":
    unittest.main()
