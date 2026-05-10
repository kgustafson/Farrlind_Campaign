from __future__ import annotations

from pathlib import Path

from farrlind_pipeline.models.schemas import ChunkManifest, StitchedTranscript, TranscriptChunk


def load_transcript_chunk(path: Path) -> TranscriptChunk:
    return TranscriptChunk.model_validate_json(path.read_text(encoding="utf-8"))


def stitch_transcripts(
    manifest: ChunkManifest,
    transcript_paths: list[Path],
    output_dir: str | Path,
) -> StitchedTranscript:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    chunks = [load_transcript_chunk(path) for path in transcript_paths]
    chunks.sort(key=lambda chunk: (chunk.start_seconds, chunk.chunk_id))

    expected_ids = {chunk.chunk_id for chunk in manifest.chunks}
    actual_ids = {chunk.chunk_id for chunk in chunks}
    warnings = [f"Missing transcript chunk: {chunk_id}" for chunk_id in sorted(expected_ids - actual_ids)]

    duplicate_pairs = []
    for previous, current in zip(chunks, chunks[1:]):
        if previous.text.strip() and previous.text.strip() == current.text.strip():
            duplicate_pairs.append(f"{previous.chunk_id}/{current.chunk_id}")
    warnings.extend(f"Duplicate adjacent transcript text: {pair}" for pair in duplicate_pairs)

    markdown_parts = [f"# Stitched Transcript: {manifest.session_id}", ""]
    for chunk in chunks:
        end = "unknown" if chunk.end_seconds is None else f"{chunk.end_seconds:.3f}"
        markdown_parts.extend(
            [
                f"## {chunk.chunk_id} ({chunk.start_seconds:.3f}s - {end}s)",
                "",
                chunk.text.strip(),
                "",
            ]
        )

    stitched = StitchedTranscript(
        session_id=manifest.session_id,
        text="\n".join(markdown_parts).strip() + "\n",
        chunks=chunks,
        warnings=warnings,
    )

    (output_dir / "stitched_transcript.md").write_text(stitched.text, encoding="utf-8")
    (output_dir / "stitched_transcript.json").write_text(stitched.model_dump_json(indent=2), encoding="utf-8")
    return stitched
