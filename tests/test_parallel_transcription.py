import tempfile
import unittest
from pathlib import Path

from raglib import parallel_transcription
from raglib.parallel_transcription import capped_worker_count, write_parallel_outputs
from scripts.transcribe_parallel import default_audio_path, default_output_path


class ParallelTranscriptionTest(unittest.TestCase):
    def test_parallel_worker_count_is_capped_at_three(self):
        self.assertEqual(capped_worker_count(0), 1)
        self.assertEqual(capped_worker_count(1), 1)
        self.assertEqual(capped_worker_count(2), 2)
        self.assertEqual(capped_worker_count(3), 3)
        self.assertEqual(capped_worker_count(5), 3)

    def test_build_chunk_specs_uses_audio_duration(self):
        original = parallel_transcription.get_duration_seconds
        parallel_transcription.get_duration_seconds = lambda _path: 370.0
        try:
            specs = parallel_transcription.build_chunk_specs(
                Path("audio/session21.wav"),
                Path("work/chunks"),
                chunk_seconds=180,
            )
        finally:
            parallel_transcription.get_duration_seconds = original

        self.assertEqual([spec.chunk_id for spec in specs], ["chunk-0001", "chunk-0002", "chunk-0003"])
        self.assertEqual([spec.duration_seconds for spec in specs], [180, 180, 10])
        self.assertEqual(specs[1].audio_path, "work/chunks/chunk-0002.wav")

    def test_write_parallel_outputs_orders_chunks_and_formats_transcript(self):
        results = [
            {
                "chunk_id": "chunk-0002",
                "start_seconds": 180.0,
                "duration_seconds": 5.0,
                "elapsed_seconds": 1.0,
                "segments": [{"start_seconds": 181.0, "end_seconds": 182.0, "text": "Second chunk"}],
            },
            {
                "chunk_id": "chunk-0001",
                "start_seconds": 0.0,
                "duration_seconds": 5.0,
                "elapsed_seconds": 1.0,
                "segments": [{"start_seconds": 1.0, "end_seconds": 2.0, "text": "First chunk"}],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript_path = root / "session21_transcript.txt"
            write_parallel_outputs(results, transcript_path, root / "chunk_json")

            self.assertEqual(
                transcript_path.read_text(encoding="utf-8"),
                "\n\n=== 00:00:00 ===\n\n"
                "[00:00:01 - 00:00:02] First chunk\n"
                "\n\n=== 00:03:00 ===\n\n"
                "[00:03:01 - 00:03:02] Second chunk\n",
            )
            self.assertTrue((root / "chunk_json" / "chunk-0001.json").exists())
            self.assertTrue((root / "chunk_json" / "chunk-0002.json").exists())

    def test_default_paths_match_campaign_pipeline(self):
        self.assertEqual(default_audio_path("session21"), Path("audio/session21.wav").resolve())
        self.assertEqual(
            default_output_path("session21"),
            Path("knowledge/Faban/raw/session21_transcript.txt").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
