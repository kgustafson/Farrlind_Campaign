import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "model_eval" / "manifest.yaml"
OLLAMA_OPTION_KEYS = {
    "temperature",
    "top_p",
    "top_k",
    "num_ctx",
    "num_predict",
    "repeat_penalty",
    "seed",
}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_repo_file(path_value: str) -> str:
    path = REPO_ROOT / path_value
    return path.read_text(encoding="utf-8")


def slug(value: str) -> str:
    return value.replace(":", "_").replace("/", "_").replace(" ", "_")


def ollama_options(run_defaults: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in run_defaults.items() if key in OLLAMA_OPTION_KEYS}


def run_ollama(model: str, prompt: str, *, options: dict[str, Any]) -> tuple[str, float]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }
    started = time.monotonic()
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=None) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(detail or str(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama API is not reachable: {exc}") from exc
    duration = time.monotonic() - started
    return (data.get("response") or "").strip(), duration


def build_prompt(prompt_text: str, transcript_text: str) -> str:
    return f"{prompt_text.rstrip()}\n\n--- TRANSCRIPT START ---\n\n{transcript_text}\n\n--- TRANSCRIPT END ---\n"


def split_transcript(transcript: str, *, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must not be negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks = []
    start = 0
    transcript_len = len(transcript)
    while start < transcript_len:
        proposed_end = min(start + chunk_size, transcript_len)
        end = proposed_end
        if proposed_end < transcript_len:
            boundary = transcript.rfind("\n\n", start + int(chunk_size * 0.65), proposed_end)
            if boundary != -1:
                end = boundary
        chunk = transcript[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= transcript_len:
            break
        start = max(0, end - overlap)
    return chunks


def build_chunk_prompt(prompt_text: str, session_name: str, chunk_text: str, chunk_index: int, chunk_count: int) -> str:
    return (
        f"{prompt_text.rstrip()}\n\n"
        f"Session: {session_name}\n"
        f"Chunk: {chunk_index} of {chunk_count}\n\n"
        f"--- TRANSCRIPT CHUNK START ---\n\n"
        f"{chunk_text}\n\n"
        f"--- TRANSCRIPT CHUNK END ---\n"
    )


def build_synthesis_prompt(prompt_text: str, session_name: str, chunk_outputs: list[str]) -> str:
    extracts = []
    for index, output in enumerate(chunk_outputs, start=1):
        extracts.append(f"--- CHUNK EXTRACT {index} START ---\n\n{output.strip()}\n\n--- CHUNK EXTRACT {index} END ---")
    return f"{prompt_text.rstrip()}\n\nSession: {session_name}\n\n" + "\n\n".join(extracts) + "\n"


def write_run_files(
    *,
    model: str,
    session_name: str,
    prompt_version: str,
    output: str,
    metadata: dict[str, Any],
) -> Path:
    output_dir = REPO_ROOT / "model_eval" / "runs" / slug(model) / prompt_version
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session_name}_output.md"
    meta_path = output_dir / f"{session_name}_metadata.json"
    output_path.write_text(output.strip() + "\n", encoding="utf-8")
    metadata["output"] = str(output_path.relative_to(REPO_ROOT))
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return output_path


def run_single_eval(
    *,
    model: str,
    session_name: str,
    session: dict[str, Any],
    transcript: str,
    prompt_path: str,
    manifest: dict[str, Any],
    limit_chars: Optional[int],
) -> dict[str, Any]:
    prompt_text = read_repo_file(prompt_path)
    full_prompt = build_prompt(prompt_text, transcript)
    output, duration = run_ollama(model, full_prompt, options=ollama_options(manifest.get("run_defaults", {})))
    prompt_version = Path(prompt_path).stem
    metadata = {
        "model": model,
        "session": session_name,
        "strategy": "single",
        "prompt": prompt_path,
        "transcript": session["transcript"],
        "gold_summary": session.get("gold_summary"),
        "duration_seconds": round(duration, 2),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "limit_chars": limit_chars,
    }
    output_path = write_run_files(
        model=model,
        session_name=session_name,
        prompt_version=prompt_version,
        output=output,
        metadata=metadata,
    )
    print(f"Wrote {output_path.relative_to(REPO_ROOT)} ({duration:.1f}s)")
    return metadata


def run_chunked_eval(
    *,
    model: str,
    session_name: str,
    session: dict[str, Any],
    transcript: str,
    chunk_prompt_path: str,
    synthesis_prompt_path: str,
    manifest: dict[str, Any],
    limit_chars: Optional[int],
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, Any]:
    chunk_prompt_text = read_repo_file(chunk_prompt_path)
    synthesis_prompt_text = read_repo_file(synthesis_prompt_path)
    prompt_version = Path(synthesis_prompt_path).stem
    output_dir = REPO_ROOT / "model_eval" / "runs" / slug(model) / prompt_version
    chunks_dir = output_dir / f"{session_name}_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chunks = split_transcript(transcript, chunk_size=chunk_size, overlap=chunk_overlap)
    chunk_outputs = []
    chunk_metadata = []
    total_duration = 0.0

    for index, chunk in enumerate(chunks, start=1):
        chunk_prompt = build_chunk_prompt(chunk_prompt_text, session_name, chunk, index, len(chunks))
        chunk_output, chunk_duration = run_ollama(model, chunk_prompt, options=ollama_options(manifest.get("run_defaults", {})))
        total_duration += chunk_duration
        chunk_path = chunks_dir / f"chunk_{index:03d}.md"
        chunk_path.write_text(chunk_output.strip() + "\n", encoding="utf-8")
        chunk_outputs.append(chunk_output)
        chunk_metadata.append(
            {
                "chunk": index,
                "chars": len(chunk),
                "duration_seconds": round(chunk_duration, 2),
                "output": str(chunk_path.relative_to(REPO_ROOT)),
            }
        )
        print(f"Wrote {chunk_path.relative_to(REPO_ROOT)} ({chunk_duration:.1f}s)")

    synthesis_prompt = build_synthesis_prompt(synthesis_prompt_text, session_name, chunk_outputs)
    output, synthesis_duration = run_ollama(model, synthesis_prompt, options=ollama_options(manifest.get("run_defaults", {})))
    total_duration += synthesis_duration
    metadata = {
        "model": model,
        "session": session_name,
        "strategy": "chunked",
        "chunk_prompt": chunk_prompt_path,
        "synthesis_prompt": synthesis_prompt_path,
        "transcript": session["transcript"],
        "gold_summary": session.get("gold_summary"),
        "duration_seconds": round(total_duration, 2),
        "synthesis_duration_seconds": round(synthesis_duration, 2),
        "chunk_count": len(chunks),
        "chunk_size_chars": chunk_size,
        "chunk_overlap_chars": chunk_overlap,
        "chunks": chunk_metadata,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "limit_chars": limit_chars,
    }
    output_path = write_run_files(
        model=model,
        session_name=session_name,
        prompt_version=prompt_version,
        output=output,
        metadata=metadata,
    )
    print(f"Wrote {output_path.relative_to(REPO_ROOT)} ({total_duration:.1f}s total)")
    return metadata


def run_eval(
    models: list[str],
    sessions: list[str],
    prompt_path: str,
    limit_chars: Optional[int] = None,
    strategy: str = "single",
    chunk_prompt_path: Optional[str] = None,
    synthesis_prompt_path: Optional[str] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> list[dict[str, Any]]:
    manifest = load_manifest()
    run_records = []
    run_defaults = manifest.get("run_defaults", {})

    for model in models:
        for session_name in sessions:
            session = manifest["sessions"][session_name]
            transcript = read_repo_file(session["transcript"])
            if limit_chars:
                transcript = transcript[:limit_chars]
            if strategy == "chunked":
                run_records.append(
                    run_chunked_eval(
                        model=model,
                        session_name=session_name,
                        session=session,
                        transcript=transcript,
                        chunk_prompt_path=chunk_prompt_path or manifest["prompts"]["chunk_prompt"],
                        synthesis_prompt_path=synthesis_prompt_path or manifest["prompts"]["synthesis_prompt"],
                        manifest=manifest,
                        limit_chars=limit_chars,
                        chunk_size=chunk_size or int(run_defaults.get("chunk_size_chars", 24000)),
                        chunk_overlap=chunk_overlap if chunk_overlap is not None else int(run_defaults.get("chunk_overlap_chars", 1500)),
                    )
                )
            else:
                run_records.append(
                    run_single_eval(
                        model=model,
                        session_name=session_name,
                        session=session,
                        transcript=transcript,
                        prompt_path=prompt_path,
                        manifest=manifest,
                        limit_chars=limit_chars,
                    )
                )

    return run_records


def main() -> None:
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description="Run local model curation bake-off through Ollama.")
    parser.add_argument("--model", action="append", choices=manifest.get("models", []), help="Model to run. Repeatable. Defaults to all manifest models.")
    parser.add_argument("--session", action="append", choices=list(manifest.get("sessions", {}).keys()), help="Session to run. Repeatable. Defaults to all manifest sessions.")
    parser.add_argument("--prompt", default=manifest["prompts"]["starting_prompt"], help="Prompt file path relative to repo root.")
    parser.add_argument("--strategy", choices=["single", "chunked"], default=manifest.get("run_defaults", {}).get("strategy", "single"), help="Run strategy. Defaults to manifest run_defaults.strategy.")
    parser.add_argument("--chunk-prompt", default=manifest.get("prompts", {}).get("chunk_prompt"), help="Chunk extraction prompt path relative to repo root.")
    parser.add_argument("--synthesis-prompt", default=manifest.get("prompts", {}).get("synthesis_prompt"), help="Chunk synthesis prompt path relative to repo root.")
    parser.add_argument("--chunk-size", type=int, default=manifest.get("run_defaults", {}).get("chunk_size_chars"), help="Chunk size in characters for chunked strategy.")
    parser.add_argument("--chunk-overlap", type=int, default=manifest.get("run_defaults", {}).get("chunk_overlap_chars"), help="Chunk overlap in characters for chunked strategy.")
    parser.add_argument("--limit-chars", type=int, help="Optional transcript character limit for smoke tests.")
    args = parser.parse_args()

    models = args.model or manifest["models"]
    sessions = args.session or list(manifest["sessions"].keys())
    run_eval(
        models,
        sessions,
        args.prompt,
        args.limit_chars,
        strategy=args.strategy,
        chunk_prompt_path=args.chunk_prompt,
        synthesis_prompt_path=args.synthesis_prompt,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )


if __name__ == "__main__":
    main()
