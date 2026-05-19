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


def run_eval(models: list[str], sessions: list[str], prompt_path: str, limit_chars: Optional[int] = None) -> list[dict[str, Any]]:
    manifest = load_manifest()
    prompt_text = read_repo_file(prompt_path)
    run_records = []

    for model in models:
        for session_name in sessions:
            session = manifest["sessions"][session_name]
            transcript = read_repo_file(session["transcript"])
            if limit_chars:
                transcript = transcript[:limit_chars]
            full_prompt = build_prompt(prompt_text, transcript)
            output, duration = run_ollama(model, full_prompt, options=ollama_options(manifest.get("run_defaults", {})))

            prompt_version = Path(prompt_path).stem
            output_dir = REPO_ROOT / "model_eval" / "runs" / slug(model) / prompt_version
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{session_name}_output.md"
            meta_path = output_dir / f"{session_name}_metadata.json"
            output_path.write_text(output + "\n", encoding="utf-8")
            metadata = {
                "model": model,
                "session": session_name,
                "prompt": prompt_path,
                "transcript": session["transcript"],
                "gold_summary": session.get("gold_summary"),
                "duration_seconds": round(duration, 2),
                "output": str(output_path.relative_to(REPO_ROOT)),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "limit_chars": limit_chars,
            }
            meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            run_records.append(metadata)
            print(f"Wrote {output_path.relative_to(REPO_ROOT)} ({duration:.1f}s)")

    return run_records


def main() -> None:
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description="Run local model curation bake-off through Ollama.")
    parser.add_argument("--model", action="append", choices=manifest.get("models", []), help="Model to run. Repeatable. Defaults to all manifest models.")
    parser.add_argument("--session", action="append", choices=list(manifest.get("sessions", {}).keys()), help="Session to run. Repeatable. Defaults to all manifest sessions.")
    parser.add_argument("--prompt", default=manifest["prompts"]["starting_prompt"], help="Prompt file path relative to repo root.")
    parser.add_argument("--limit-chars", type=int, help="Optional transcript character limit for smoke tests.")
    args = parser.parse_args()

    models = args.model or manifest["models"]
    sessions = args.session or list(manifest["sessions"].keys())
    run_eval(models, sessions, args.prompt, args.limit_chars)


if __name__ == "__main__":
    main()
