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
    "known_location_mentions",
    "new_location_candidates",
    "rejected_candidates",
    "uncertainties",
]
LOCATION_ALIASES = {
    "cater": "catur",
    "jennifers coven": "druid retreat",
    "jennifer s coven": "druid retreat",
    "druid coven": "druid retreat",
    "catur shoreline": "coast near catur",
    "shoreline near catur": "coast near catur",
}


def session_number(session_name: str) -> int:
    match = re.search(r"(\d+)$", session_name)
    if not match:
        raise ValueError(f"Could not parse session number from {session_name!r}")
    return int(match.group(1))


def output_path(session_name: str) -> Path:
    return OUTPUT_DIR / f"{session_name}_locations.json"


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


def normalized_name(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    for alias, canonical in LOCATION_ALIASES.items():
        normalized = re.sub(rf"\b{re.escape(alias)}\b", canonical, normalized)
    return LOCATION_ALIASES.get(normalized, normalized)


def source_contains_any(source_text: str, values: list[Any]) -> bool:
    source = normalized_name(source_text)
    return any(value and normalized_name(value) in source for value in values)


def mentioned_as_values(item: dict[str, Any]) -> list[str]:
    values = item.get("mentioned_as", [])
    if isinstance(values, str):
        return [values]
    if isinstance(values, list):
        return [str(value) for value in values if value]
    return []


def location_registry() -> list[dict[str, Any]]:
    registry = []
    for row in canon.location_rows():
        registry.append({
            "id": row.get("id"),
            "name": row.get("name") or "",
            "location_type": row.get("location_type") or "",
            "parent_location": row.get("parent_location") or "",
            "description": row.get("description") or "",
            "is_underwater": bool(row.get("is_underwater")),
            "is_feywild": bool(row.get("is_feywild")),
            "first_visited_session": row.get("first_visited_session"),
            "notes": row.get("notes") or "",
        })
    return registry


def npc_name_registry() -> list[str]:
    return [row.get("name") for row in canon.npc_rows() if row.get("name")]


def registry_indexes(registry: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id = {}
    by_name = {}
    for row in registry:
        if row.get("id") is not None:
            by_id[int(row["id"])] = row
        normalized = normalized_name(row.get("name"))
        if normalized:
            by_name[normalized] = row
    return by_id, by_name


def canonical_matches_registry(item: dict[str, Any], registry_row: dict[str, Any]) -> bool:
    return normalized_name(item.get("canonical_name")) == normalized_name(registry_row.get("name"))


def reject_candidate(document: dict[str, Any], candidate: dict[str, Any], reason: str) -> None:
    document["rejected_candidates"].append({
        "text": candidate.get("proposed_name") or candidate.get("text") or "unknown candidate",
        "reason": reason,
    })


def existing_known_location_ids(document: dict[str, Any]) -> set[int]:
    ids = set()
    for item in document["known_location_mentions"]:
        try:
            ids.add(int(item["location_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def candidate_to_known_mention(candidate: dict[str, Any], registry_row: dict[str, Any], session_name: str) -> dict[str, Any]:
    return {
        "location_id": registry_row.get("id"),
        "canonical_name": registry_row.get("name"),
        "mentioned_as": [candidate.get("proposed_name")],
        "new_information": candidate.get("description") or "Mentioned in this session; no new canon update proposed.",
        "session_number": session_number(session_name),
        "location_type": candidate.get("location_type") or registry_row.get("location_type") or "",
        "parent_location": candidate.get("parent_location") or registry_row.get("parent_location") or "",
        "is_underwater": bool(candidate.get("is_underwater") or registry_row.get("is_underwater")),
        "is_feywild": bool(candidate.get("is_feywild") or registry_row.get("is_feywild")),
        "confidence": candidate.get("confidence") or "medium",
        "evidence": candidate.get("evidence") or "",
    }


def normalize_extraction(document: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key in EXPECTED_TOP_LEVEL_KEYS:
        value = document.get(key, [])
        normalized[key] = value if isinstance(value, list) else []
    return normalized


def postprocess_extraction(
    document: dict[str, Any],
    registry: list[dict[str, Any]],
    session_name: str,
    source_text: str = "",
) -> tuple[dict[str, Any], list[str]]:
    cleaned = normalize_extraction(document)
    warnings = []
    by_id, by_name = registry_indexes(registry)

    known_mentions = []
    for item in cleaned["known_location_mentions"]:
        try:
            location_id = int(item.get("location_id"))
        except (TypeError, ValueError):
            warnings.append(f"Dropped known location mention with invalid location_id: {item.get('canonical_name')}")
            continue
        registry_row = by_id.get(location_id)
        if not registry_row:
            warnings.append(f"Dropped known location mention with unknown location_id {location_id}: {item.get('canonical_name')}")
            continue
        if not canonical_matches_registry(item, registry_row):
            warnings.append(
                f"Dropped known location mention whose canonical name does not match location_id {location_id}: "
                f"{item.get('canonical_name')} != {registry_row.get('name')}"
            )
            continue
        if source_text and not source_contains_any(source_text, [registry_row.get("name"), item.get("canonical_name")]):
            warnings.append(f"Dropped known location mention not present in session source: {registry_row.get('name')}")
            continue
        item["canonical_name"] = registry_row.get("name")
        known_mentions.append(item)

    cleaned["known_location_mentions"] = known_mentions
    known_ids = existing_known_location_ids(cleaned)
    new_candidates = []
    for candidate in cleaned["new_location_candidates"]:
        proposed_name = candidate.get("proposed_name", "")
        normalized_proposed = normalized_name(proposed_name)
        registry_row = by_name.get(normalized_proposed)

        if registry_row:
            registry_id = int(registry_row["id"])
            if registry_id not in known_ids:
                if source_text and not source_contains_any(source_text, [proposed_name, registry_row.get("name")]):
                    reject_candidate(cleaned, candidate, f"Existing location candidate not present in session source: {registry_row.get('name')}.")
                    warnings.append(f"Rejected existing location candidate not present in source: {proposed_name}")
                else:
                    cleaned["known_location_mentions"].append(candidate_to_known_mention(candidate, registry_row, session_name))
                    known_ids.add(registry_id)
                    warnings.append(f"Moved existing location candidate to known mention: {proposed_name}")
            else:
                reject_candidate(cleaned, candidate, f"Duplicate of existing location: {registry_row.get('name')}.")
                warnings.append(f"Rejected duplicate existing location candidate: {proposed_name}")
            continue

        if source_text and not source_contains_any(source_text, [proposed_name]):
            reject_candidate(cleaned, candidate, "Candidate name not found in session source.")
            warnings.append(f"Rejected location candidate not present in source: {proposed_name}")
            continue

        new_candidates.append(candidate)

    cleaned["new_location_candidates"] = new_candidates
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
            raise ValueError(f"Unsupported location extraction source: {source}")
        selected = [(source, known[source])]

    sources = []
    for label, path in selected:
        sources.append({
            "label": label,
            "path": str(path),
            "text": read_text(path),
        })
    return sources


def build_prompt(
    session_name: str,
    sources: list[dict[str, str]],
    registry: list[dict[str, Any]],
    npcs: list[str],
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
        load_prompt("extract_locations").strip(),
        f"Session name: {session_name}",
        f"Session number: {session_number(session_name)}",
        "Campaign metadata JSON:",
        json.dumps(campaign_metadata, indent=2, ensure_ascii=False),
        "Current location registry JSON:",
        json.dumps(registry, indent=2, ensure_ascii=False),
        "Current NPC names JSON, for avoiding person/place confusion:",
        json.dumps(npcs, indent=2, ensure_ascii=False),
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


def extract_locations(session_name: str, model: Optional[str] = None, source: str = "auto") -> Path:
    model = model or os.environ.get("FARRLIND_LOCATION_EXTRACTOR_MODEL", DEFAULT_MODEL)
    sources = load_session_sources(session_name, source)
    campaign_metadata = load_campaign_metadata()
    registry = location_registry()
    npcs = npc_name_registry()
    prompt = build_prompt(session_name, sources, registry, npcs, campaign_metadata)

    print(f"Extracting location candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_output = generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)
    duration = time.monotonic() - started
    source_text = "\n\n".join(source["text"] for source in sources)
    extracted, guardrail_warnings = postprocess_extraction(
        extract_json_object(raw_output),
        registry,
        session_name,
        source_text,
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
        "location_registry_count": len(registry),
        "npc_registry_count": len(npcs),
        "duration_seconds": round(duration, 2),
        "guardrail_warning_count": len(guardrail_warnings),
        "guardrail_warnings": guardrail_warnings,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(path),
    }, indent=2) + "\n")
    print(f"Location extraction written to: {path}")
    print(f"Location extraction metadata written to: {metadata_path}")
    return path
