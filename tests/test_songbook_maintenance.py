import unittest

from scripts import songbook_maintenance


class SongbookMaintenanceTest(unittest.TestCase):
    def test_title_similarity_uses_meaningful_tokens(self):
        score = songbook_maintenance.title_similarity(
            "The Battle of Balrog Square",
            "Battle at Balrog",
        )

        self.assertGreaterEqual(score, 0.5)

    def test_classify_song_issue_flags_missing_prompt(self):
        song = {
            "title": "The Missing Prompt",
            "suno_prompt": "",
            "lyrics_local_path": "campaigns/farrlind/songbook/Urgan_Wyrmbane/lyrics.md",
            "mp3_local_path": "campaigns/farrlind/songbook/Urgan_Wyrmbane/song.mp3",
            "style": "war_chant",
            "category": "heroic_saga",
            "short_description": "An old heroic chant.",
        }

        self.assertIn("missing prompt", songbook_maintenance.classify_song_issue(song))

    def test_build_song_opportunities_excludes_sessions_with_known_missing_mentions(self):
        sessions = [{"session_number": 19, "title": "Balrog Square", "summary": ""}]
        events = [
            {
                "session_number": 19,
                "session_title": "Balrog Square",
                "event_type": "combat",
                "significance": 5,
                "description": "The party defeats a dragon in Balrog Square.",
            }
        ]
        songs = [{"title": "Urgan Wyrmbane", "written_session": None}]

        opportunities = songbook_maintenance.build_song_opportunities(
            sessions,
            events,
            songs,
            max_items=5,
            excluded_sessions={19},
        )

        self.assertEqual([], opportunities)

    def test_duplicate_theme_groups_returns_categories_with_more_than_two_songs(self):
        songs = [
            {"song_number": 1, "title": "A", "category": "lament"},
            {"song_number": 2, "title": "B", "category": "lament"},
            {"song_number": 3, "title": "C", "category": "lament"},
            {"song_number": 4, "title": "D", "category": "humor"},
        ]

        groups = songbook_maintenance.duplicate_theme_groups(songs)

        self.assertEqual("lament", groups[0][0])
        self.assertEqual(3, len(groups[0][1]))


if __name__ == "__main__":
    unittest.main()
