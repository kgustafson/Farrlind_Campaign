import unittest

from raglib import merge


class MergeEventsTest(unittest.TestCase):
    def test_split_event_blocks_keeps_untimestamped_valid_events(self):
        text = """
EVENT:
timestamp:
event_type: recap
summary: Party arrives at the Night Lotus Inn and Spa.
actors: The party
location: Night Lotus Inn and Spa
importance: medium
confidence: high
verify:
"""

        blocks = merge.split_event_blocks(text)

        self.assertEqual(len(blocks), 1)
        self.assertIn("Party arrives", blocks[0])
        self.assertTrue(merge.is_valid_event(blocks[0]))


if __name__ == "__main__":
    unittest.main()
