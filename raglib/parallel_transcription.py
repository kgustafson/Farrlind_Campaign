from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_MODEL_SIZE = "large-v3"
DEFAULT_CHUNK_SECONDS = 180
DEFAULT_MAX_WORKERS = 2
MAX_PARALLEL_WORKERS = 3


@dataclass(frozen=True)
class ChunkSpec:
    chunk_id: str
    start_seconds: float
    duration_seconds: float
    audio_path: str

    @property
    def end_seconds(self) -> float:
        return self.start_seconds + self.duration_seconds


def capped_worker_count(requested_workers: int) -> int:
    return max(1, min(requested_workers, MAX_PARALLEL_WORKERS))


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def progress(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_duration_seconds(audio_path: str | Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def extract_chunk(audio_path: str | Path, start: float, duration: float, out_wav: str | Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(audio_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(out_wav),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        print("\nFFmpeg failed.")
        print("Command was:")
        print(" ".join(cmd))
        print("\nFFmpeg error output:")
        print(exc.stderr)
        raise


def build_chunk_specs(
    audio_file: Path,
    chunks_dir: Path,
    chunk_seconds: int,
    limit_seconds: float | None = None,
) -> list[ChunkSpec]:
    total_duration = get_duration_seconds(audio_file)
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
    started = time.perf_counter()
    for spec in specs:
        progress(f"materialize {spec.chunk_id} {fmt_time(spec.start_seconds)}-{fmt_time(spec.end_seconds)}")
        Path(spec.audio_path).parent.mkdir(parents=True, exist_ok=True)
        extract_chunk(audio_file, spec.start_seconds, spec.duration_seconds, spec.audio_path)
    return time.perf_counter() - started


def transcribe_parallel_chunk(spec: dict, model_size: str) -> dict:
    from faster_whisper import WhisperModel

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


def transcribe_parallel_audio(
    audio_file: str | Path,
    output_path: str | Path,
    work_dir: str | Path,
    model_size: str = DEFAULT_MODEL_SIZE,
    chunk_seconds: int = DEFAULT_CHUNK_SECONDS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    limit_seconds: float | None = None,
) -> dict:
    audio_file = Path(audio_file)
    output_path = Path(output_path)
    work_dir = Path(work_dir)
    max_workers = capped_worker_count(max_workers)

    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    chunks_dir = work_dir / "chunks"
    chunk_json_dir = work_dir / "chunk_json"
    specs = build_chunk_specs(audio_file, chunks_dir, chunk_seconds, limit_seconds)
    write_json(work_dir / "chunk_manifest.json", [asdict(spec) for spec in specs])

    progress(
        f"start parallel transcription model={model_size} "
        f"workers={max_workers} chunks={len(specs)} output={output_path}"
    )
    split_elapsed = materialize_chunks(audio_file, specs)
    started = time.perf_counter()
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(transcribe_parallel_chunk, asdict(spec), model_size) for spec in specs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            progress(f"parallel done {result['chunk_id']} elapsed={result['elapsed_seconds']:.2f}s")
    transcribe_elapsed = time.perf_counter() - started
    write_parallel_outputs(results, output_path, chunk_json_dir)

    total_elapsed = split_elapsed + transcribe_elapsed
    audio_seconds = sum(spec.duration_seconds for spec in specs)
    summary = {
        "architecture": "parallel_workers",
        "elapsed_seconds": total_elapsed,
        "split_elapsed_seconds": split_elapsed,
        "transcribe_elapsed_seconds": transcribe_elapsed,
        "audio_seconds": audio_seconds,
        "speed_factor": audio_seconds / total_elapsed if total_elapsed else None,
        "model": model_size,
        "chunk_seconds": chunk_seconds,
        "max_workers": max_workers,
        "audio_file": str(audio_file),
        "output_path": str(output_path),
        "work_dir": str(work_dir),
        "chunks": sorted(results, key=lambda row: row["start_seconds"]),
    }
    write_json(work_dir / "summary.json", summary)
    progress(f"done parallel transcription elapsed={total_elapsed:.2f}s")
    return summary


def transcribe_parallel_audio_temp(
    audio_file: str | Path,
    output_path: str | Path,
    model_size: str = DEFAULT_MODEL_SIZE,
    chunk_seconds: int = DEFAULT_CHUNK_SECONDS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    keep_work_dir: str | Path | None = None,
    limit_seconds: float | None = None,
) -> dict:
    if keep_work_dir is not None:
        return transcribe_parallel_audio(
            audio_file=audio_file,
            output_path=output_path,
            work_dir=keep_work_dir,
            model_size=model_size,
            chunk_seconds=chunk_seconds,
            max_workers=max_workers,
            limit_seconds=limit_seconds,
        )

    temp_dir = Path(tempfile.mkdtemp(prefix="farrlind-transcribe-"))
    try:
        summary = transcribe_parallel_audio(
            audio_file=audio_file,
            output_path=output_path,
            work_dir=temp_dir,
            model_size=model_size,
            chunk_seconds=chunk_seconds,
            max_workers=max_workers,
            limit_seconds=limit_seconds,
        )
        summary["work_dir"] = ""
        return summary
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
