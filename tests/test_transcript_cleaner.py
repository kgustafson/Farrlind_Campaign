import unittest

from raglib.transcript_cleaner import clean_source_text, clean_transcript_for_extraction


class TranscriptCleanerTest(unittest.TestCase):
    def test_podcast_transcript_trims_ads_recap_and_post_show(self):
        text = "\n".join([
            "[00:00:00] This sponsor offer ends today.",
            "[00:01:00] We are back with this episode.",
            "[00:02:00] how about a quick recap?",
            "[00:03:00] A dire wolf from last session was killed.",
            "[00:04:00] And that is where we are now.",
            "[00:04:01] The party finds three dead commoners.",
            "[00:05:00] The zombies rise.",
            "[00:06:00] That is where we'll end our session.",
            "[00:07:00] If you would like to listen to the short rest, go to Patreon.",
            "[00:08:00] Time to thank our benevolent council of elders.",
        ])

        result = clean_transcript_for_extraction(text)

        self.assertIn("podcast markers detected", result.notes)
        self.assertNotIn("sponsor offer", result.text)
        self.assertNotIn("dire wolf from last session", result.text)
        self.assertIn("The party finds three dead commoners.", result.text)
        self.assertIn("That is where we'll end our session.", result.text)
        self.assertNotIn("benevolent council", result.text)

    def test_raw_table_recording_trims_opening_recap_without_podcast_markers(self):
        text = "\n".join([
            "[00:00:00] Last time, the party entered the tomb.",
            "[00:01:00] That is where we left off.",
            "[00:02:00] The party opens the stone door.",
            "[00:03:00] We'll end our session there.",
            "[00:04:00] People pack up dice.",
        ])

        result = clean_transcript_for_extraction(text)

        self.assertNotIn("podcast markers detected", result.notes)
        self.assertNotIn("Last time, the party entered the tomb.", result.text)
        self.assertNotIn("That is where we left off.", result.text)
        self.assertIn("We'll end our session there.", result.text)
        self.assertIn("The party opens the stone door.", result.text)
        self.assertNotIn("People pack up dice.", result.text)

    def test_non_transcript_source_is_unchanged(self):
        self.assertEqual(clean_source_text("final_summary", "unchanged"), "unchanged")


if __name__ == "__main__":
    unittest.main()
