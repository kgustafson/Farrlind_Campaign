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
    compact_registry_for_chunk,
    looks_like_party_interpretation,
    looks_like_unconfirmed_party_framing,
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
    "known_thread_mentions",
    "new_thread_candidates",
    "rejected_candidates",
    "uncertainties",
]


def session_number(session_name: str) -> int:
    match = re.search(r"(\d+)$", session_name)
    if not match:
        raise ValueError(f"Could not parse session number from {session_name!r}")
    return int(match.group(1))


def output_path(session_name: str) -> Path:
    return OUTPUT_DIR / f"{session_name}_open_threads.json"


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


def normalized_name(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def valid_status_codes() -> set[str]:
    return {row["code"] for row in canon.open_thread_statuses()}


def valid_thread_types() -> set[str]:
    return set(canon.open_thread_types())


def open_thread_registry() -> list[dict[str, Any]]:
    registry = []
    for row in canon.open_thread_rows():
        registry.append({
            "id": row.get("id"),
            "title": row.get("title") or "",
            "thread_type": row.get("thread_type") or "",
            "status": row.get("status") or "",
            "first_session": row.get("first_session"),
            "last_session": row.get("last_session"),
            "related_location": row.get("related_location") or "",
            "description": row.get("description") or "",
            "resolution": row.get("resolution") or "",
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


def normalize_session_value(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value in (None, "", "unknown"):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_status(value: Any) -> str:
    status = str(value or "open").strip()
    return status if status in valid_status_codes() else "open"


def normalize_thread_type(value: Any) -> str:
    thread_type = str(value or "lore_mystery").strip()
    return thread_type if thread_type in valid_thread_types() else "lore_mystery"


def reject_candidate(document: dict[str, Any], candidate: dict[str, Any], reason: str) -> None:
    document["rejected_candidates"].append({
        "text": candidate.get("proposed_title") or candidate.get("text") or "unknown candidate",
        "reason": reason,
    })


def existing_known_thread_ids(document: dict[str, Any]) -> set[int]:
    ids = set()
    for item in document["known_thread_mentions"]:
        try:
            ids.add(int(item["thread_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def candidate_to_known_mention(candidate: dict[str, Any], registry_row: dict[str, Any], session_name: str) -> dict[str, Any]:
    current_session = session_number(session_name)
    return {
        "thread_id": registry_row.get("id"),
        "canonical_title": registry_row.get("title"),
        "new_information": candidate.get("description") or "Mentioned in this session; no new canon update proposed.",
        "thread_type": normalize_thread_type(candidate.get("thread_type") or registry_row.get("thread_type")),
        "status": normalize_status(candidate.get("status") or registry_row.get("status")),
        "first_session": normalize_session_value(candidate.get("first_session"), registry_row.get("first_session") or current_session),
        "last_session": normalize_session_value(candidate.get("last_session"), current_session),
        "related_location": candidate.get("related_location") or registry_row.get("related_location") or "",
        "resolution": candidate.get("resolution") or "",
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
    warnings: list[str] = []
    by_id, by_title = registry_indexes(registry)
    current_session = session_number(session_name)

    known_mentions = []
    for item in cleaned["known_thread_mentions"]:
        try:
            thread_id = int(item.get("thread_id"))
        except (TypeError, ValueError):
            warnings.append(f"Dropped known thread mention with invalid thread_id: {item.get('canonical_title')}")
            continue
        registry_row = by_id.get(thread_id)
        if not registry_row:
            warnings.append(f"Dropped known thread mention with unknown thread_id {thread_id}: {item.get('canonical_title')}")
            continue
        if not canonical_matches_registry(item, registry_row):
            warnings.append(
                f"Dropped known thread mention whose canonical title does not match thread_id {thread_id}: "
                f"{item.get('canonical_title')} != {registry_row.get('title')}"
            )
            continue
        item["canonical_title"] = registry_row.get("title")
        item["thread_type"] = normalize_thread_type(item.get("thread_type") or registry_row.get("thread_type"))
        item["status"] = normalize_status(item.get("status") or registry_row.get("status"))
        item["first_session"] = normalize_session_value(item.get("first_session"), registry_row.get("first_session"))
        item["last_session"] = normalize_session_value(item.get("last_session"), current_session)
        known_mentions.append(item)

    cleaned["known_thread_mentions"] = known_mentions
    known_ids = existing_known_thread_ids(cleaned)
    new_candidates = []
    for candidate in cleaned["new_thread_candidates"]:
        proposed_title = candidate.get("proposed_title", "")
        if looks_like_party_interpretation(
            candidate,
            source_text,
            name_fields=["proposed_title"],
            context_fields=["description", "notes", "evidence"],
        ) or looks_like_unconfirmed_party_framing(
            candidate,
            source_text,
            name_fields=["proposed_title"],
            context_fields=["description", "notes", "evidence"],
        ):
            reject_candidate(
                cleaned,
                candidate,
                "Appears to be a party joke, misunderstanding, or theory rather than durable unresolved campaign business.",
            )
            warnings.append(f"Rejected party-interpretation open thread candidate: {rejection_text(candidate, 'proposed_title')}")
            continue
        registry_row = by_title.get(normalized_name(proposed_title))

        if registry_row:
            registry_id = int(registry_row["id"])
            if registry_id not in known_ids:
                cleaned["known_thread_mentions"].append(candidate_to_known_mention(candidate, registry_row, session_name))
                known_ids.add(registry_id)
                warnings.append(f"Moved existing open thread candidate to known mention: {proposed_title}")
            else:
                reject_candidate(cleaned, candidate, f"Duplicate of existing open thread: {registry_row.get('title')}.")
                warnings.append(f"Rejected duplicate existing open thread candidate: {proposed_title}")
            continue

        if not proposed_title:
            reject_candidate(cleaned, candidate, "Candidate is missing a proposed title.")
            warnings.append("Rejected open thread candidate missing proposed title.")
            continue

        candidate["thread_type"] = normalize_thread_type(candidate.get("thread_type"))
        candidate["status"] = normalize_status(candidate.get("status"))
        candidate["first_session"] = normalize_session_value(candidate.get("first_session"), current_session)
        candidate["last_session"] = normalize_session_value(candidate.get("last_session"), current_session)
        new_candidates.append(candidate)

    cleaned["new_thread_candidates"] = new_candidates
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
            raise ValueError(f"Unsupported open thread extraction source: {source}")
        selected = [(source, known[source])]

    return [{"label": label, "path": str(path), "text": clean_source_text(label, read_text(path))} for label, path in selected]


def build_prompt(
    session_name: str,
    sources: list[dict[str, str]],
    registry: list[dict[str, Any]],
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
        load_prompt("extract_open_threads").strip(),
        f"Session name: {session_name}",
        f"Session number: {session_number(session_name)}",
        "Campaign metadata JSON:",
        json.dumps(campaign_metadata, indent=2, ensure_ascii=False),
        "Current open thread registry JSON:",
        json.dumps(registry, indent=2, ensure_ascii=False),
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


def extract_open_threads(session_name: str, model: Optional[str] = None, source: str = "auto") -> Path:
    model = model or os.environ.get("FARRLIND_OPEN_THREAD_EXTRACTOR_MODEL", DEFAULT_MODEL)
    sources = load_session_sources(session_name, source)
    campaign_metadata = load_campaign_metadata()
    registry = open_thread_registry()
    locations = canon.locations()
    source_sets = chunk_source_sets(sources)

    print(f"Extracting open thread candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_documents = []
    registry_rows_sent = []
    for index, source_set in enumerate(source_sets, start=1):
        if len(source_sets) > 1:
            print(f"  Open thread transcript chunk {index}/{len(source_sets)}...")
        chunk_text = "\n\n".join(item["text"] for item in source_set)
        prompt_registry = compact_registry_for_chunk(
            chunk_text,
            registry,
            identity_fields=["title"],
            keep_fields=["id", "title", "thread_type", "status", "related_location"],
        ) if len(source_sets) > 1 else registry
        prompt_locations = compact_name_list_for_chunk(chunk_text, locations) if len(source_sets) > 1 else locations
        prompt_metadata = compact_campaign_metadata(campaign_metadata) if len(source_sets) > 1 else campaign_metadata
        registry_rows_sent.append(len(prompt_registry))
        prompt = build_prompt(session_name, source_set, prompt_registry, prompt_locations, prompt_metadata)
        raw_documents.append(extract_json_object(generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)))
    duration = time.monotonic() - started
    extracted, guardrail_warnings = postprocess_extraction(
        merge_extraction_documents(raw_documents, EXPECTED_TOP_LEVEL_KEYS),
        registry,
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
        "registry_rows_sent": registry_rows_sent,
        "avg_registry_rows_sent": round(sum(registry_rows_sent) / len(registry_rows_sent), 2) if registry_rows_sent else 0,
        "campaign_metadata": str(campaign_metadata_path()),
        "open_thread_count": len(registry),
        "location_count": len(locations),
        "duration_seconds": round(duration, 2),
        "guardrail_warning_count": len(guardrail_warnings),
        "guardrail_warnings": guardrail_warnings,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(path),
    }, indent=2) + "\n")
    print(f"Open thread extraction written to: {path}")
    print(f"Open thread extraction metadata written to: {metadata_path}")
    return path
