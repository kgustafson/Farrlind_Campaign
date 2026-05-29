import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from raglib.config import BASE, CLEAN, RAW
from raglib.extraction_hygiene import (
    chunk_source_sets,
    compact_campaign_metadata,
    compact_name_list_for_chunk,
    looks_like_party_interpretation,
    merge_extraction_documents,
    rejection_text,
)
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import generate
from raglib.prompts import load_prompt
from raglib.transcript_cleaner import clean_source_text
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
        ("session_spine", CLEAN / f"{session_name}_spine.yaml"),
        ("narrative", CLEAN / f"{session_name}_narrative.md"),
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


def normalized_key(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    normalized = re.sub(r"\b(zombies)\b", "zombie", normalized)
    normalized = re.sub(r"\b(wolves)\b", "wolf", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def enemy_family(enemy: dict[str, Any]) -> str:
    enemy_type = normalized_key(enemy.get("enemy_type"))
    name = normalized_key(enemy.get("name"))
    value = enemy_type or name
    if value.endswith("s") and len(value) > 3:
        value = value[:-1]
    return value or "unknown"


def encounter_enemy_families(encounter: dict[str, Any]) -> tuple[str, ...]:
    families = sorted({
        enemy_family(enemy)
        for enemy in encounter.get("enemies", [])
        if enemy_family(enemy) != "unknown"
    })
    return tuple(families)


def merge_text_values(*values: Any, separator: str = " ") -> str:
    seen = set()
    parts = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized = normalized_key(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        parts.append(text)
    return separator.join(parts)


def better_title(current: str, candidate: str) -> str:
    generic_words = {"attack", "ambush", "sequence", "combat", "fight", "encounter"}

    def score(value: str) -> tuple[int, int]:
        tokens = set(normalized_key(value).split())
        specific_tokens = tokens - generic_words
        return (len(specific_tokens), len(value))

    return candidate if score(candidate) > score(current) else current


def better_confidence(current: str, candidate: str) -> str:
    rank = {"low": 1, "medium": 2, "high": 3}
    return candidate if rank.get(candidate, 0) > rank.get(current, 0) else current


def better_outcome(current: str, candidate: str) -> str:
    rank = {
        "unknown": 0,
        "cliffhanger": 1,
        "ongoing": 2,
        "encountered": 3,
        "fled": 4,
        "escaped": 4,
        "resolved": 5,
        "defeated": 6,
        "enemies_defeated": 6,
    }
    return candidate if rank.get(candidate, 0) > rank.get(current, 0) else current


def merge_enemy_rows(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing["name"] = better_title(existing.get("name", ""), incoming.get("name", ""))
    existing["enemy_type"] = existing.get("enemy_type") or incoming.get("enemy_type") or ""
    for key in ["quantity", "quantity_killed"]:
        values = [value for value in [existing.get(key), incoming.get(key)] if value is not None]
        existing[key] = max(values) if values else None
    existing["outcome"] = better_outcome(existing.get("outcome") or "unknown", incoming.get("outcome") or "unknown")
    existing["confidence"] = better_confidence(existing.get("confidence") or "medium", incoming.get("confidence") or "medium")
    existing["notes"] = merge_text_values(existing.get("notes"), incoming.get("notes"), separator=" ")
    return existing


def merge_combat_encounter(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    existing["title"] = better_title(existing.get("title", ""), incoming.get("title", ""))
    existing["subtype"] = existing.get("subtype") or incoming.get("subtype") or ""
    existing["location"] = better_title(existing.get("location", ""), incoming.get("location", ""))
    existing["participants"] = merge_text_values(existing.get("participants"), incoming.get("participants"), separator="; ")
    existing["outcome"] = better_outcome(existing.get("outcome") or "unknown", incoming.get("outcome") or "unknown")
    existing["confidence"] = better_confidence(existing.get("confidence") or "medium", incoming.get("confidence") or "medium")
    existing["notes"] = merge_text_values(existing.get("notes"), incoming.get("notes"), separator=" ")
    existing["evidence"] = merge_text_values(existing.get("evidence"), incoming.get("evidence"), separator=" ")

    enemy_rows = {enemy_family(enemy): enemy for enemy in existing.get("enemies", [])}
    for enemy in incoming.get("enemies", []):
        family = enemy_family(enemy)
        if family in enemy_rows:
            merge_enemy_rows(enemy_rows[family], enemy)
        else:
            existing.setdefault("enemies", []).append(enemy)
            enemy_rows[family] = enemy
    return existing


def duplicate_combat_key(encounter: dict[str, Any]) -> Optional[tuple[Any, tuple[str, ...]]]:
    families = encounter_enemy_families(encounter)
    if not families:
        return None
    return (encounter.get("session_number"), families)


def merge_duplicate_combat_encounters(encounters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    merged: list[dict[str, Any]] = []
    by_key: dict[tuple[Any, tuple[str, ...]], dict[str, Any]] = {}
    warnings: list[str] = []

    for encounter in encounters:
        key = duplicate_combat_key(encounter)
        if key is None:
            merged.append(encounter)
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = encounter
            merged.append(encounter)
            continue
        previous_title = existing.get("title") or "untitled combat"
        incoming_title = encounter.get("title") or "untitled combat"
        merge_combat_encounter(existing, encounter)
        warnings.append(f"Merged duplicate combat encounter candidates: {previous_title} + {incoming_title}")

    return merged, warnings


def normalize_extraction(document: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key in EXPECTED_TOP_LEVEL_KEYS:
        value = document.get(key, [])
        normalized[key] = value if isinstance(value, list) else []
    return normalized


def postprocess_extraction(
    document: dict[str, Any],
    session_name: str,
    source_text: str = "",
) -> tuple[dict[str, Any], list[str]]:
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
        if looks_like_party_interpretation(
            encounter,
            source_text,
            name_fields=["title"],
            context_fields=["participants", "outcome", "notes", "evidence"],
        ):
            cleaned["rejected_candidates"].append({
                "text": rejection_text(encounter, "title", "evidence"),
                "reason": "Appears to be a party joke, misunderstanding, or theory rather than a confirmed combat encounter.",
            })
            warnings.append(f"Rejected party-interpretation combat encounter: {title}")
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
                "quantity_killed": normalize_quantity(enemy.get("quantity_killed")),
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

    cleaned["proposed_combat_encounters"], merge_warnings = merge_duplicate_combat_encounters(encounters)
    warnings.extend(merge_warnings)
    return cleaned, warnings


def load_session_sources(session_name: str, source: str = "auto") -> list[dict[str, str]]:
    if source == "auto":
        selected = [(label, path) for label, path in source_candidates(session_name) if path.exists()]
        if not selected:
            raise FileNotFoundError(f"No session source files found for {session_name}.")
        if any(label == "final_summary" for label, _path in selected):
            selected = [item for item in selected if item[0] in {"final_summary", "diary"}]
        elif any(label == "curated_packet" for label, _path in selected):
            selected = [item for item in selected if item[0] in {"session_spine", "narrative", "draft_summary", "curated_packet", "diary"}]
        else:
            selected = selected[:2]
    else:
        known = dict(source_candidates(session_name))
        if source not in known:
            raise ValueError(f"Unsupported combat encounter extraction source: {source}")
        selected = [(source, known[source])]

    return [{"label": label, "path": str(path), "text": clean_source_text(label, read_text(path))} for label, path in selected]


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
    source_sets = chunk_source_sets(sources)

    print(f"Extracting combat encounter candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_documents = []
    location_names_sent = []
    for index, source_set in enumerate(source_sets, start=1):
        if len(source_sets) > 1:
            print(f"  Combat transcript chunk {index}/{len(source_sets)}...")
        chunk_text = "\n\n".join(item["text"] for item in source_set)
        prompt_locations = compact_name_list_for_chunk(chunk_text, locations) if len(source_sets) > 1 else locations
        prompt_metadata = compact_campaign_metadata(campaign_metadata) if len(source_sets) > 1 else campaign_metadata
        location_names_sent.append(len(prompt_locations))
        prompt = build_prompt(session_name, source_set, prompt_locations, prompt_metadata)
        raw_documents.append(extract_json_object(generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)))
    duration = time.monotonic() - started
    extracted, guardrail_warnings = postprocess_extraction(
        merge_extraction_documents(raw_documents, EXPECTED_TOP_LEVEL_KEYS),
        session_name,
        "\n\n".join(source["text"] for source in sources),
    )
    path = output_path(session_name)
    write_text(path, json.dumps(extracted, indent=2, ensure_ascii=False) + "\n")

    metadata_path = path.with_name(f"{path.stem}_metadata.json")
    write_text(metadata_path, json.dumps({
        "session": session_name,
        "model": model,
        "source": source,
        "sources": [{"label": item["label"], "path": item["path"], "chars": len(item["text"])} for item in sources],
        "chunked": len(source_sets) > 1,
        "chunk_count": len(source_sets),
        "location_names_sent": location_names_sent,
        "avg_location_names_sent": round(sum(location_names_sent) / len(location_names_sent), 2) if location_names_sent else 0,
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
