from __future__ import annotations

import math
import wave
from datetime import datetime, timezone
from pathlib import Path

from farrlind_pipeline.models.schemas import AudioChunk, ChunkManifest


def audio_duration_seconds(source_audio: Path) -> float | None:
    """Return WAV duration when it can be read without external dependencies."""
    if source_audio.suffix.lower() != ".wav":
        return None

    try:
        with wave.open(str(source_audio), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
    except (wave.Error, EOFError, FileNotFoundError):
        return None

    if rate <= 0:
        return None
    return frames / float(rate)


def build_chunks(
    source_audio: Path,
    chunk_seconds: int = 900,
    overlap_seconds: int = 15,
) -> list[AudioChunk]:
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive.")
    if overlap_seconds < 0:
        raise ValueError("overlap_seconds cannot be negative.")
    if overlap_seconds >= chunk_seconds:
        raise ValueError("overlap_seconds must be smaller than chunk_seconds.")

    duration = audio_duration_seconds(source_audio)
    if duration is None or duration <= 0:
        return [
            AudioChunk(
                chunk_id="chunk-0001",
                source_audio=source_audio,
                chunk_audio_path=None,
                start_seconds=0.0,
                end_seconds=None,
                materialized=False,
            )
        ]

    chunks: list[AudioChunk] = []
    stride = chunk_seconds - overlap_seconds
    total = max(1, math.ceil(max(duration - overlap_seconds, 0) / stride))

    for index in range(total):
        start = float(index * stride)
        end = min(start + chunk_seconds, duration)
        chunks.append(
            AudioChunk(
                chunk_id=f"chunk-{index + 1:04d}",
                source_audio=source_audio,
                chunk_audio_path=None,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                materialized=False,
            )
        )
        if end >= duration:
            break

    return chunks


def split_audio(
    source_audio: str | Path,
    output_dir: str | Path,
    session_id: str,
    chunk_seconds: int = 900,
    overlap_seconds: int = 15,
) -> ChunkManifest:
    source_audio = Path(source_audio)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = ChunkManifest(
        session_id=session_id,
        source_audio=source_audio,
        output_dir=output_dir,
        chunk_seconds=chunk_seconds,
        overlap_seconds=overlap_seconds,
        created_at=datetime.now(timezone.utc),
        chunks=build_chunks(source_audio, chunk_seconds, overlap_seconds),
    )

    manifest_path = output_dir / "chunk_manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
