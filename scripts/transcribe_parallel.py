from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.config import RAW
from raglib.audio import resolve_session_audio_path
from raglib.parallel_transcription import (
    DEFAULT_CHUNK_SECONDS,
    DEFAULT_MAX_WORKERS,
    DEFAULT_MODEL_SIZE,
    capped_worker_count,
    transcribe_parallel_audio_temp,
)


def default_audio_path(session_name: str) -> Path:
    return resolve_session_audio_path(session_name)


def default_output_path(session_name: str) -> Path:
    return RAW / f"{session_name}_transcript.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe Farrlind session audio with parallel faster-whisper workers.")
    parser.add_argument("session_name", help="Session name, e.g. session21.")
    parser.add_argument("--audio-file", type=Path, default=None, help="Defaults to campaigns/<campaign>/audio/<session_name> using the first existing supported audio extension.")
    parser.add_argument("--output", type=Path, default=None, help="Defaults to campaigns/<campaign>/raw/<session_name>_transcript.txt.")
    parser.add_argument("--model", default=DEFAULT_MODEL_SIZE)
    parser.add_argument("--chunk-seconds", type=int, default=DEFAULT_CHUNK_SECONDS)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Optional directory to keep chunk audio, chunk JSON, manifest, and summary artifacts.",
    )
    parser.add_argument("--limit-seconds", type=float, default=None, help="Optional smoke-test limit.")
    return parser.parse_args()


def run_transcription(args: argparse.Namespace) -> dict:
    audio_file = args.audio_file or default_audio_path(args.session_name)
    output_path = args.output or default_output_path(args.session_name)
    summary = transcribe_parallel_audio_temp(
        audio_file=audio_file,
        output_path=output_path,
        model_size=args.model,
        chunk_seconds=args.chunk_seconds,
        max_workers=capped_worker_count(args.max_workers),
        keep_work_dir=args.work_dir,
        limit_seconds=args.limit_seconds,
    )
    return summary


def main() -> None:
    summary = run_transcription(parse_args())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
