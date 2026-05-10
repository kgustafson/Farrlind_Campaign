from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from faster_whisper import WhisperModel

from scripts.transcribe import extract_chunk, fmt_time, get_duration_seconds


DEFAULT_MODEL_SIZE = "large-v3"
DEFAULT_CHUNK_SECONDS = 180
DEFAULT_MAX_WORKERS = 2
MAX_PARALLEL_WORKERS = 2


@dataclass(frozen=True)
class ChunkSpec:
    chunk_id: str
    start_seconds: float
    duration_seconds: float
    audio_path: str

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds


def now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def shell_quote(value: Path | str) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def benchmark_root(base_dir: Path, session_id: str) -> Path:
    return base_dir / session_id / now_id()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_chunk_specs(
    audio_file: Path,
    chunks_dir: Path,
    chunk_seconds: int,
    limit_seconds: float | None,
) -> list[ChunkSpec]:
    total_duration = get_duration_seconds(str(audio_file))
    if limit_seconds is not None:
        total_duration = min(total_duration, limit_seconds)

    specs: list[ChunkSpec] = []
    chunk_start = 0.0
    index = 1
    while chunk_start < total_duration:
        duration = min(chunk_seconds, total_duration - chunk_start)
        chunk_path = chunks_dir / f"chunk-{index:04d}.wav"
        specs.append(
            ChunkSpec(
                chunk_id=f"chunk-{index:04d}",
                start_seconds=chunk_start,
                duration_seconds=duration,
                audio_path=str(chunk_path),
            )
        )
        chunk_start += chunk_seconds
        index += 1
    return specs


def materialize_chunks(audio_file: Path, specs: list[ChunkSpec]) -> float:
    start = time.perf_counter()
    for spec in specs:
        Path(spec.audio_path).parent.mkdir(parents=True, exist_ok=True)
        extract_chunk(str(audio_file), spec.start_seconds, spec.duration_seconds, spec.audio_path)
    return time.perf_counter() - start


def transcribe_existing_sequential(
    audio_file: Path,
    output_path: Path,
    model_size: str,
    chunk_seconds: int,
    limit_seconds: float | None,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    total_duration = get_duration_seconds(str(audio_file))
    if limit_seconds is not None:
        total_duration = min(total_duration, limit_seconds)

    chunk_timings = []
    started = time.perf_counter()
    with output_path.open("w", encoding="utf-8") as out:
        chunk_start = 0.0
        index = 1
        while chunk_start < total_duration:
            chunk_len = min(chunk_seconds, total_duration - chunk_start)
            chunk_timer = time.perf_counter()
            tmp_path = output_path.parent / f"_existing_chunk_{index:04d}.wav"
            try:
                extract_chunk(str(audio_file), chunk_start, chunk_len, str(tmp_path))
                segments, _info = model.transcribe(
                    str(tmp_path),
                    task="transcribe",
                    beam_size=5,
                    temperature=0.0,
                    vad_filter=True,
                )
                out.write(f"\n\n=== {fmt_time(chunk_start)} ===\n\n")
                for segment in segments:
                    absolute_start = chunk_start + segment.start
                    absolute_end = chunk_start + segment.end
                    text = segment.text.strip()
                    if not text:
                        continue
                    out.write(f"[{fmt_time(absolute_start)} - {fmt_time(absolute_end)}] {text}\n")
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
            chunk_timings.append(
                {
                    "chunk_id": f"chunk-{index:04d}",
                    "start_seconds": chunk_start,
                    "duration_seconds": chunk_len,
                    "elapsed_seconds": time.perf_counter() - chunk_timer,
                }
            )
            chunk_start += chunk_seconds
            index += 1

    elapsed = time.perf_counter() - started
    return {
        "architecture": "existing_sequential",
        "elapsed_seconds": elapsed,
        "audio_seconds": total_duration,
        "speed_factor": total_duration / elapsed if elapsed else None,
        "output_path": str(output_path),
        "chunks": chunk_timings,
    }


def transcribe_parallel_chunk(spec: dict, model_size: str) -> dict:
    chunk = ChunkSpec(**spec)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    started = time.perf_counter()
    segments, _info = model.transcribe(
        chunk.audio_path,
        task="transcribe",
        beam_size=5,
        temperature=0.0,
        vad_filter=True,
    )
    rows = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        rows.append(
            {
                "start_seconds": chunk.start_seconds + segment.start,
                "end_seconds": chunk.start_seconds + segment.end,
                "text": text,
            }
        )
    return {
        "chunk_id": chunk.chunk_id,
        "start_seconds": chunk.start_seconds,
        "duration_seconds": chunk.duration_seconds,
        "elapsed_seconds": time.perf_counter() - started,
        "segments": rows,
    }


def write_parallel_outputs(results: list[dict], transcript_path: Path, chunk_json_dir: Path) -> None:
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_json_dir.mkdir(parents=True, exist_ok=True)
    sorted_results = sorted(results, key=lambda row: row["start_seconds"])
    with transcript_path.open("w", encoding="utf-8") as out:
        for result in sorted_results:
            write_json(chunk_json_dir / f"{result['chunk_id']}.json", result)
            out.write(f"\n\n=== {fmt_time(result['start_seconds'])} ===\n\n")
            for segment in result["segments"]:
                out.write(
                    f"[{fmt_time(segment['start_seconds'])} - "
                    f"{fmt_time(segment['end_seconds'])}] {segment['text']}\n"
                )


def transcribe_parallel_workers(
    audio_file: Path,
    output_dir: Path,
    model_size: str,
    chunk_seconds: int,
    max_workers: int,
    limit_seconds: float | None,
) -> dict:
    chunks_dir = output_dir / "chunks"
    chunk_json_dir = output_dir / "chunk_json"
    transcript_path = output_dir / "parallel_transcript.txt"
    specs = build_chunk_specs(audio_file, chunks_dir, chunk_seconds, limit_seconds)
    manifest = [asdict(spec) for spec in specs]
    write_json(output_dir / "chunk_manifest.json", manifest)

    split_elapsed = materialize_chunks(audio_file, specs)
    started = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(transcribe_parallel_chunk, asdict(spec), model_size) for spec in specs]
        for future in as_completed(futures):
            results.append(future.result())
    transcribe_elapsed = time.perf_counter() - started
    write_parallel_outputs(results, transcript_path, chunk_json_dir)

    total_elapsed = split_elapsed + transcribe_elapsed
    audio_seconds = sum(spec.duration_seconds for spec in specs)
    return {
        "architecture": "parallel_workers",
        "elapsed_seconds": total_elapsed,
        "split_elapsed_seconds": split_elapsed,
        "transcribe_elapsed_seconds": transcribe_elapsed,
        "audio_seconds": audio_seconds,
        "speed_factor": audio_seconds / total_elapsed if total_elapsed else None,
        "max_workers": max_workers,
        "output_path": str(transcript_path),
        "chunks": sorted(results, key=lambda row: row["start_seconds"]),
    }


def write_report(run_dir: Path, summary: dict) -> None:
    lines = [
        "# Transcription Architecture Benchmark",
        "",
        f"Audio: `{summary['audio_file']}`",
        f"Model: `{summary['model']}`",
        f"Chunk seconds: `{summary['chunk_seconds']}`",
        f"Limit seconds: `{summary['limit_seconds']}`",
        "",
        "| Architecture | Elapsed | Audio | Speed Factor | Output |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for result in summary["results"]:
        speed = result["speed_factor"]
        speed_text = "" if speed is None else f"{speed:.3f}x"
        lines.append(
            f"| {result['architecture']} | {result['elapsed_seconds']:.2f}s | "
            f"{result['audio_seconds']:.2f}s | {speed_text} | `{result['output_path']}` |"
        )
    lines.append("")
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def capped_worker_count(requested_workers: int) -> int:
    return max(1, min(requested_workers, MAX_PARALLEL_WORKERS))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark existing and parallel transcription architectures in isolation.")
    parser.add_argument("audio_file", type=Path)
    parser.add_argument("--session-id", default="session20")
    parser.add_argument("--output-root", type=Path, default=Path("benchmarks/transcription"))
    parser.add_argument("--architecture", choices=["existing", "parallel", "both"], default="both")
    parser.add_argument("--model", default=DEFAULT_MODEL_SIZE)
    parser.add_argument("--chunk-seconds", type=int, default=DEFAULT_CHUNK_SECONDS)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--limit-seconds", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.max_workers = capped_worker_count(args.max_workers)
    return args


def main() -> None:
    args = parse_args()
    run_dir = benchmark_root(args.output_root, args.session_id)

    if args.dry_run:
        duration = get_duration_seconds(str(args.audio_file))
        limit = min(duration, args.limit_seconds) if args.limit_seconds is not None else duration
        planned_chunks = build_chunk_specs(args.audio_file, run_dir / "dry-run-chunks", args.chunk_seconds, args.limit_seconds)
        print(json.dumps({
            "audio_file": str(args.audio_file),
            "duration_seconds": duration,
            "benchmarked_audio_seconds": limit,
            "chunk_seconds": args.chunk_seconds,
            "planned_chunks": len(planned_chunks),
            "output_run_dir": str(run_dir),
            "architecture": args.architecture,
            "model": args.model,
            "max_workers": args.max_workers,
        }, indent=2))
        return

    run_dir.mkdir(parents=True, exist_ok=True)
    results = []
    if args.architecture in {"existing", "both"}:
        results.append(
            transcribe_existing_sequential(
                audio_file=args.audio_file,
                output_path=run_dir / "existing" / "existing_transcript.txt",
                model_size=args.model,
                chunk_seconds=args.chunk_seconds,
                limit_seconds=args.limit_seconds,
            )
        )
    if args.architecture in {"parallel", "both"}:
        results.append(
            transcribe_parallel_workers(
                audio_file=args.audio_file,
                output_dir=run_dir / "parallel",
                model_size=args.model,
                chunk_seconds=args.chunk_seconds,
                max_workers=args.max_workers,
                limit_seconds=args.limit_seconds,
            )
        )

    summary = {
        "audio_file": str(args.audio_file),
        "session_id": args.session_id,
        "model": args.model,
        "chunk_seconds": args.chunk_seconds,
        "limit_seconds": args.limit_seconds,
        "output_run_dir": str(run_dir),
        "results": results,
    }
    write_json(run_dir / "summary.json", summary)
    write_report(run_dir, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
