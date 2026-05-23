import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from raglib.config import BASE, CLEAN, RAW
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import generate
from raglib.prompts import load_prompt
from web_review.services import canon


DEFAULT_MODEL = "gemma4:e2b"
OUTPUT_DIR = BASE / "extracted"
OLLAMA_OPTIONS = {
    "temperature": 0.1,
    "top_p": 0.9,
    "num_ctx": 32768,
}
EXPECTED_TOP_LEVEL_KEYS = [
    "proposed_combat_encounters",
    "rejected_candidates",
    "uncertainties",
]


def session_number(session_name: str) -> int:
    match = re.search(r"(\d+)$", session_name)
    if not match:
        raise ValueError(f"Could not parse session number from {session_name!r}")
    return int(match.group(1))


def output_path(session_name: str) -> Path:
    return OUTPUT_DIR / f"{session_name}_combat_encounters.json"


def source_candidates(session_name: str) -> list[tuple[str, Path]]:
    return [
        ("final_summary", BASE / "final" / f"{session_name}_summary.md"),
        ("curated_packet", CLEAN / f"{session_name}_curated.md"),
        ("draft_summary", CLEAN / f"{session_name}_summary.md"),
        ("diary", CLEAN / f"{session_name}_diary.md"),
        ("transcript", RAW / f"{session_name}_transcript.txt"),
    ]


def campaign_metadata_path() -> Path:
    return BASE / "campaign.yaml"


def load_campaign_metadata() -> dict[str, Any]:
    path = campaign_metadata_path()
    if not path.exists():
        return {}
    import yaml

    return yaml.safe_load(read_text(path)) or {}


def normalize_quantity(value: Any) -> Optional[int]:
    if value in (None, "", "unknown"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_extraction(document: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key in EXPECTED_TOP_LEVEL_KEYS:
        value = document.get(key, [])
        normalized[key] = value if isinstance(value, list) else []
    return normalized


def postprocess_extraction(document: dict[str, Any], session_name: str) -> tuple[dict[str, Any], list[str]]:
    cleaned = normalize_extraction(document)
    warnings: list[str] = []
    encounters: list[dict[str, Any]] = []
    default_session_number = session_number(session_name)

    for encounter in cleaned["proposed_combat_encounters"]:
        title = (encounter.get("title") or "").strip()
        if not title:
            cleaned["rejected_candidates"].append({
                "text": encounter.get("evidence") or "untitled combat candidate",
                "reason": "Combat encounter candidate is missing a title.",
            })
            warnings.append("Rejected combat encounter candidate missing title.")
            continue
        proposed_session_number = normalize_quantity(encounter.get("session_number")) or default_session_number
        if proposed_session_number != default_session_number:
            cleaned["rejected_candidates"].append({
                "text": title,
                "reason": f"Candidate belongs to session {proposed_session_number}, not {default_session_number}.",
            })
            warnings.append(f"Rejected combat encounter from wrong session: {title}")
            continue
        evidence = encounter.get("evidence") or ""
        if "Loaded from encounters.yaml" in evidence or "Loaded from enemy_encounters.yaml" in evidence:
            cleaned["rejected_candidates"].append({
                "text": title,
                "reason": "Candidate evidence came from existing registry notes rather than session source.",
            })
            warnings.append(f"Rejected registry-sourced combat encounter: {title}")
            continue

        enemies = []
        for enemy in encounter.get("enemies") or []:
            name = (enemy.get("name") or "").strip()
            if not name:
                warnings.append(f"Dropped unnamed enemy row for encounter: {title}")
                continue
            enemies.append({
                "name": name,
                "enemy_type": (enemy.get("enemy_type") or "").strip(),
                "quantity": normalize_quantity(enemy.get("quantity")),
                "outcome": (enemy.get("outcome") or "unknown").strip(),
                "confidence": (enemy.get("confidence") or encounter.get("confidence") or "medium").strip(),
                "notes": (enemy.get("notes") or "").strip(),
            })

        encounter["title"] = title
        encounter["session_number"] = proposed_session_number
        encounter["subtype"] = (encounter.get("subtype") or "").strip()
        encounter["location"] = (encounter.get("location") or "").strip()
        encounter["participants"] = (encounter.get("participants") or "").strip()
        encounter["outcome"] = (encounter.get("outcome") or "unknown").strip()
        encounter["confidence"] = (encounter.get("confidence") or "medium").strip()
        encounter["notes"] = (encounter.get("notes") or "").strip()
        encounter["enemies"] = enemies
        encounters.append(encounter)

    cleaned["proposed_combat_encounters"] = encounters
    return cleaned, warnings


def load_session_sources(session_name: str, source: str = "auto") -> list[dict[str, str]]:
    if source == "auto":
        selected = [(label, path) for label, path in source_candidates(session_name) if path.exists()]
        if not selected:
            raise FileNotFoundError(f"No session source files found for {session_name}.")
        if any(label == "final_summary" for label, _path in selected):
            selected = [item for item in selected if item[0] in {"final_summary", "diary"}]
        elif any(label == "curated_packet" for label, _path in selected):
            selected = [item for item in selected if item[0] in {"curated_packet", "diary"}]
        else:
            selected = selected[:2]
    else:
        known = dict(source_candidates(session_name))
        if source not in known:
            raise ValueError(f"Unsupported combat encounter extraction source: {source}")
        selected = [(source, known[source])]

    return [{"label": label, "path": str(path), "text": read_text(path)} for label, path in selected]


def build_prompt(
    session_name: str,
    sources: list[dict[str, str]],
    locations: list[str],
    campaign_metadata: dict[str, Any],
) -> str:
    source_blocks = []
    for source in sources:
        source_blocks.append(
            f"--- SOURCE {source['label']} ({source['path']}) START ---\n"
            f"{source['text'].strip()}\n"
            f"--- SOURCE {source['label']} END ---"
        )
    return "\n\n".join([
        load_prompt("extract_combat_encounters").strip(),
        f"Session name: {session_name}",
        f"Session number: {session_number(session_name)}",
        "Campaign metadata JSON:",
        json.dumps(campaign_metadata, indent=2, ensure_ascii=False),
        "Current location names JSON:",
        json.dumps(locations, indent=2, ensure_ascii=False),
        "Session source material:",
        "\n\n".join(source_blocks),
    ])


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start:end + 1])


def extract_combat_encounters(session_name: str, model: Optional[str] = None, source: str = "auto") -> Path:
    model = model or os.environ.get("FARRLIND_COMBAT_EXTRACTOR_MODEL", DEFAULT_MODEL)
    sources = load_session_sources(session_name, source)
    campaign_metadata = load_campaign_metadata()
    locations = canon.locations()
    prompt = build_prompt(session_name, sources, locations, campaign_metadata)

    print(f"Extracting combat encounter candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_output = generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)
    duration = time.monotonic() - started
    extracted, guardrail_warnings = postprocess_extraction(
        extract_json_object(raw_output),
        session_name,
    )
    path = output_path(session_name)
    write_text(path, json.dumps(extracted, indent=2, ensure_ascii=False) + "\n")

    metadata_path = path.with_name(f"{path.stem}_metadata.json")
    write_text(metadata_path, json.dumps({
        "session": session_name,
        "model": model,
        "source": source,
        "sources": [{"label": item["label"], "path": item["path"], "chars": len(item["text"])} for item in sources],
        "campaign_metadata": str(campaign_metadata_path()),
        "location_count": len(locations),
        "duration_seconds": round(duration, 2),
        "guardrail_warning_count": len(guardrail_warnings),
        "guardrail_warnings": guardrail_warnings,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(path),
    }, indent=2) + "\n")
    print(f"Combat encounter extraction written to: {path}")
    print(f"Combat encounter extraction metadata written to: {metadata_path}")
    return path
