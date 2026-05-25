import unittest

from raglib.campaign_metadata_seed import build_campaign_metadata_seed_sql, glossary_entry_is_npc


class CampaignMetadataSeedTest(unittest.TestCase):
    def test_glossary_entry_is_npc_filters_places_and_party_nicknames(self):
        self.assertTrue(glossary_entry_is_npc({
            "term": "Ismark",
            "note": "Kolyan's son; meets the party at Blood on the Vine.",
        }))
        self.assertTrue(glossary_entry_is_npc({
            "term": "Bluetooth",
            "note": "Onyx's imp familiar.",
        }))
        self.assertFalse(glossary_entry_is_npc({
            "term": "Barovia",
            "note": "Gothic domain where the party is trapped.",
        }))
        self.assertFalse(glossary_entry_is_npc({
            "term": "Trinyvale Triplets",
            "note": "Party nickname for Jens, Onyx, and Nyack.",
        }))

    def test_build_seed_sql_includes_party_and_npc_glossary_entries(self):
        sql = build_campaign_metadata_seed_sql({
            "party": [{
                "character_name": "Jens",
                "full_name": "Jens Lyndelle",
                "player_name": "Brian Murphy",
                "class": "bard",
                "race": "elf",
                "aliases": ["Jens Lindell"],
                "notes": "One of the Triplets.",
            }],
            "glossary": [
                {
                    "term": "Ismark",
                    "note": "Kolyan's son.",
                    "aliases": ["Ismark the Lesser"],
                },
                {
                    "term": "Barovia",
                    "note": "Gothic domain.",
                    "aliases": ["Borovia"],
                },
            ],
        })

        self.assertIn("INSERT INTO player_character", sql)
        self.assertIn("'Jens Lyndelle'", sql)
        self.assertIn("INSERT INTO npc", sql)
        self.assertIn("'Ismark'", sql)
        self.assertNotIn("'Barovia'", sql)
        self.assertIn("Seeded from campaign.yaml", sql)


if __name__ == "__main__":
    unittest.main()
