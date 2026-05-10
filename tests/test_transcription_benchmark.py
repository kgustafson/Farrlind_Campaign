import unittest

from scripts.benchmark_transcription_architectures import capped_worker_count


class TranscriptionBenchmarkTest(unittest.TestCase):
    def test_parallel_worker_count_is_capped_at_three(self):
        self.assertEqual(capped_worker_count(0), 1)
        self.assertEqual(capped_worker_count(1), 1)
        self.assertEqual(capped_worker_count(2), 2)
        self.assertEqual(capped_worker_count(3), 3)
        self.assertEqual(capped_worker_count(5), 3)


if __name__ == "__main__":
    unittest.main()
