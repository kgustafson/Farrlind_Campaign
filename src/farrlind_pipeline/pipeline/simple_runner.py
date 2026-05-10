from __future__ import annotations

import argparse
from pathlib import Path

from farrlind_pipeline.audio.split import split_audio
from farrlind_pipeline.models.schemas import PipelineRunResult
from farrlind_pipeline.transcription.stitch import stitch_transcripts
from farrlind_pipeline.transcription.transcribe_parallel import transcribe_parallel_placeholder
from farrlind_pipeline.validation.validate import validate_transcript_placeholder


def run_pipeline(
    source_audio: str | Path,
    work_dir: str | Path,
    session_id: str,
    chunk_seconds: int = 900,
    overlap_seconds: int = 15,
) -> PipelineRunResult:
    work_dir = Path(work_dir)
    chunks_dir = work_dir / "chunks"
    transcripts_dir = work_dir / "transcripts"
    stitched_dir = work_dir / "stitched"
    validation_dir = work_dir / "validation"

    manifest = split_audio(
        source_audio=source_audio,
        output_dir=chunks_dir,
        session_id=session_id,
        chunk_seconds=chunk_seconds,
        overlap_seconds=overlap_seconds,
    )
    transcript_paths = transcribe_parallel_placeholder(manifest, transcripts_dir)
    stitched = stitch_transcripts(manifest, transcript_paths, stitched_dir)
    validation = validate_transcript_placeholder(stitched, validation_dir)

    status = "needs_review" if validation.findings else "succeeded"
    return PipelineRunResult(
        session_id=session_id,
        status=status,
        manifest_path=chunks_dir / "chunk_manifest.json",
        transcript_chunk_paths=transcript_paths,
        stitched_markdown_path=stitched_dir / "stitched_transcript.md",
        stitched_json_path=stitched_dir / "stitched_transcript.json",
        validation_json_path=validation_dir / "validation_report.json",
        validation_markdown_path=validation_dir / "validation_report.md",
        warnings=stitched.warnings + [finding.message for finding in validation.findings],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the plain Python Farrlind worker pipeline skeleton.")
    parser.add_argument("source_audio", help="Source audio file path.")
    parser.add_argument("--session-id", required=True, help="Stable session id, e.g. session21.")
    parser.add_argument("--work-dir", required=True, help="Directory for intermediate outputs.")
    parser.add_argument("--chunk-seconds", type=int, default=900)
    parser.add_argument("--overlap-seconds", type=int, default=15)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_pipeline(
        source_audio=args.source_audio,
        work_dir=args.work_dir,
        session_id=args.session_id,
        chunk_seconds=args.chunk_seconds,
        overlap_seconds=args.overlap_seconds,
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
