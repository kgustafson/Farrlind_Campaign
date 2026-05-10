from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from farrlind_pipeline.models.schemas import ChunkManifest, TranscriptChunk, TranscriptSegment


def transcribe_chunk_placeholder(chunk, output_dir: Path, model_name: str) -> Path:
    transcript = TranscriptChunk(
        chunk_id=chunk.chunk_id,
        source_audio=chunk.source_audio,
        chunk_audio_path=chunk.chunk_audio_path,
        start_seconds=chunk.start_seconds,
        end_seconds=chunk.end_seconds,
        text=f"[placeholder transcript for {chunk.chunk_id}]",
        segments=[
            TranscriptSegment(
                start_seconds=chunk.start_seconds,
                end_seconds=chunk.end_seconds,
                text=f"[placeholder transcript for {chunk.chunk_id}]",
            )
        ],
        model_name=model_name,
        confidence=None,
        status="needs_review",
        metadata={"placeholder": True},
    )

    output_path = output_dir / f"{chunk.chunk_id}.json"
    output_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def transcribe_parallel_placeholder(
    manifest: ChunkManifest,
    output_dir: str | Path,
    max_workers: int = 4,
    model_name: str = "placeholder-transcriber",
) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    worker_count = max(1, min(max_workers, len(manifest.chunks) or 1))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        paths = list(
            executor.map(
                lambda chunk: transcribe_chunk_placeholder(chunk, output_dir, model_name),
                manifest.chunks,
            )
        )
    return sorted(paths)
