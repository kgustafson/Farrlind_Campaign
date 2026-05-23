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
    "known_lore_mentions",
    "new_lore_candidates",
    "rejected_candidates",
    "uncertainties",
]


def session_number(session_name: str) -> int:
    match = re.search(r"(\d+)$", session_name)
    if not match:
        raise ValueError(f"Could not parse session number from {session_name!r}")
    return int(match.group(1))


def output_path(session_name: str) -> Path:
    return OUTPUT_DIR / f"{session_name}_lore_items.json"


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
    return re.sub(r"\s+", " ", normalized)


def lore_registry() -> list[dict[str, Any]]:
    registry = []
    for row in canon.lore_item_rows():
        registry.append({
            "id": row.get("id"),
            "title": row.get("title") or "",
            "category": row.get("category") or "",
            "description": row.get("description") or "",
            "source_npc": row.get("source_npc") or "",
            "discovered_session": row.get("discovered_session"),
            "is_confirmed": bool(row.get("is_confirmed")),
            "notes": row.get("notes") or "",
        })
    return registry


def registry_indexes(registry: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id = {}
    by_title = {}
    for row in registry:
        if row.get("id") is not None:
            by_id[int(row["id"])] = row
        normalized = normalized_name(row.get("title"))
        if normalized:
            by_title[normalized] = row
    return by_id, by_title


def canonical_matches_registry(item: dict[str, Any], registry_row: dict[str, Any]) -> bool:
    return normalized_name(item.get("canonical_title")) == normalized_name(registry_row.get("title"))


def reject_candidate(document: dict[str, Any], candidate: dict[str, Any], reason: str) -> None:
    document["rejected_candidates"].append({
        "text": candidate.get("proposed_title") or candidate.get("text") or "unknown candidate",
        "reason": reason,
    })


def existing_known_lore_ids(document: dict[str, Any]) -> set[int]:
    ids = set()
    for item in document["known_lore_mentions"]:
        try:
            ids.add(int(item["lore_item_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def candidate_to_known_mention(candidate: dict[str, Any], registry_row: dict[str, Any], session_name: str) -> dict[str, Any]:
    return {
        "lore_item_id": registry_row.get("id"),
        "canonical_title": registry_row.get("title"),
        "new_information": candidate.get("description") or "Mentioned in this session; no new canon update proposed.",
        "session_number": session_number(session_name),
        "category": candidate.get("category") or registry_row.get("category") or "",
        "source_npc": candidate.get("source_npc") or registry_row.get("source_npc") or "",
        "is_confirmed": bool(candidate.get("is_confirmed") if candidate.get("is_confirmed") is not None else registry_row.get("is_confirmed")),
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
) -> tuple[dict[str, Any], list[str]]:
    cleaned = normalize_extraction(document)
    warnings = []
    by_id, by_title = registry_indexes(registry)

    known_mentions = []
    for item in cleaned["known_lore_mentions"]:
        try:
            lore_item_id = int(item.get("lore_item_id"))
        except (TypeError, ValueError):
            warnings.append(f"Dropped known lore mention with invalid lore_item_id: {item.get('canonical_title')}")
            continue
        registry_row = by_id.get(lore_item_id)
        if not registry_row:
            warnings.append(f"Dropped known lore mention with unknown lore_item_id {lore_item_id}: {item.get('canonical_title')}")
            continue
        if not canonical_matches_registry(item, registry_row):
            warnings.append(
                f"Dropped known lore mention whose canonical title does not match lore_item_id {lore_item_id}: "
                f"{item.get('canonical_title')} != {registry_row.get('title')}"
            )
            continue
        item["canonical_title"] = registry_row.get("title")
        known_mentions.append(item)

    cleaned["known_lore_mentions"] = known_mentions
    known_ids = existing_known_lore_ids(cleaned)
    new_candidates = []
    for candidate in cleaned["new_lore_candidates"]:
        proposed_title = candidate.get("proposed_title", "")
        registry_row = by_title.get(normalized_name(proposed_title))

        if registry_row:
            registry_id = int(registry_row["id"])
            if registry_id not in known_ids:
                cleaned["known_lore_mentions"].append(candidate_to_known_mention(candidate, registry_row, session_name))
                known_ids.add(registry_id)
                warnings.append(f"Moved existing lore candidate to known mention: {proposed_title}")
            else:
                reject_candidate(cleaned, candidate, f"Duplicate of existing lore item: {registry_row.get('title')}.")
                warnings.append(f"Rejected duplicate existing lore candidate: {proposed_title}")
            continue

        if not proposed_title:
            reject_candidate(cleaned, candidate, "Candidate is missing a proposed title.")
            warnings.append("Rejected lore candidate missing proposed title.")
            continue

        new_candidates.append(candidate)

    cleaned["new_lore_candidates"] = new_candidates
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
            raise ValueError(f"Unsupported lore item extraction source: {source}")
        selected = [(source, known[source])]

    return [{"label": label, "path": str(path), "text": read_text(path)} for label, path in selected]


def build_prompt(
    session_name: str,
    sources: list[dict[str, str]],
    registry: list[dict[str, Any]],
    npcs: list[str],
    locations: list[str],
    artifacts: list[str],
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
        load_prompt("extract_lore_items").strip(),
        f"Session name: {session_name}",
        f"Session number: {session_number(session_name)}",
        "Campaign metadata JSON:",
        json.dumps(campaign_metadata, indent=2, ensure_ascii=False),
        "Current lore registry JSON:",
        json.dumps(registry, indent=2, ensure_ascii=False),
        "Current NPC names JSON, for source/entity disambiguation:",
        json.dumps(npcs, indent=2, ensure_ascii=False),
        "Current location names JSON, for place/lore disambiguation:",
        json.dumps(locations, indent=2, ensure_ascii=False),
        "Current artifact names JSON, for artifact/lore disambiguation:",
        json.dumps(artifacts, indent=2, ensure_ascii=False),
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


def extract_lore_items(session_name: str, model: Optional[str] = None, source: str = "auto") -> Path:
    model = model or os.environ.get("FARRLIND_LORE_ITEM_EXTRACTOR_MODEL", DEFAULT_MODEL)
    sources = load_session_sources(session_name, source)
    campaign_metadata = load_campaign_metadata()
    registry = lore_registry()
    npcs = [row.get("name") for row in canon.npc_rows() if row.get("name")]
    locations = canon.locations()
    artifacts = [row.get("name") for row in canon.artifact_rows() if row.get("name")]
    prompt = build_prompt(session_name, sources, registry, npcs, locations, artifacts, campaign_metadata)

    print(f"Extracting lore item candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_output = generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)
    duration = time.monotonic() - started
    extracted, guardrail_warnings = postprocess_extraction(
        extract_json_object(raw_output),
        registry,
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
        "lore_registry_count": len(registry),
        "npc_registry_count": len(npcs),
        "location_count": len(locations),
        "artifact_registry_count": len(artifacts),
        "duration_seconds": round(duration, 2),
        "guardrail_warning_count": len(guardrail_warnings),
        "guardrail_warnings": guardrail_warnings,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(path),
    }, indent=2) + "\n")
    print(f"Lore item extraction written to: {path}")
    print(f"Lore item extraction metadata written to: {metadata_path}")
    return path
