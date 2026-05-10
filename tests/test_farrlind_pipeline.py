import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from farrlind_pipeline.audio.split import split_audio
from farrlind_pipeline.models.schemas import ChunkManifest
from farrlind_pipeline.pipeline.simple_runner import run_pipeline


def write_silent_wav(path: Path, seconds: float, sample_rate: int = 8000) -> None:
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)


class FarrlindPipelineTest(unittest.TestCase):
    def test_split_audio_writes_manifest_with_overlapping_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "session21.wav"
            write_silent_wav(source, seconds=10)

            manifest = split_audio(source, root / "chunks", "session21", chunk_seconds=4, overlap_seconds=1)

            self.assertEqual(manifest.session_id, "session21")
            self.assertEqual([chunk.chunk_id for chunk in manifest.chunks], ["chunk-0001", "chunk-0002", "chunk-0003"])
            self.assertEqual(manifest.chunks[1].start_seconds, 3.0)
            manifest_path = root / "chunks" / "chunk_manifest.json"
            self.assertTrue(manifest_path.exists())
            loaded = ChunkManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(loaded.chunks), 3)

    def test_simple_runner_writes_placeholder_pipeline_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "session21.wav"
            write_silent_wav(source, seconds=3)

            result = run_pipeline(
                source_audio=source,
                work_dir=root / "work",
                session_id="session21",
                chunk_seconds=10,
                overlap_seconds=1,
            )

            self.assertEqual(result.status, "needs_review")
            self.assertTrue(result.manifest_path.exists())
            self.assertEqual(len(result.transcript_chunk_paths), 1)
            self.assertTrue(result.stitched_markdown_path.exists())
            self.assertTrue(result.stitched_json_path.exists())
            self.assertTrue(result.validation_json_path.exists())
            self.assertTrue(result.validation_markdown_path.exists())
            self.assertIn("placeholder transcription worker", result.validation_markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
