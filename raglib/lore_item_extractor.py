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
    neutralize_party_framed_update,
    neutralize_interpretive_update,
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


def source_contains_any(source_text: str, values: list[Any]) -> bool:
    source = normalized_name(source_text)
    return any(value and normalized_name(value) in source for value in values)


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


def known_mention_to_candidate(item: dict[str, Any], session_name: str) -> dict[str, Any]:
    return {
        "proposed_title": item.get("canonical_title") or item.get("proposed_title") or "",
        "category": item.get("category") or "",
        "description": item.get("new_information") or item.get("description") or "Mentioned in this session.",
        "source_npc": item.get("source_npc") or "",
        "discovered_session": session_number(session_name),
        "is_confirmed": bool(item.get("is_confirmed")),
        "confidence": item.get("confidence") or "medium",
        "evidence": item.get("evidence") or "",
    }


def known_mention_is_source_grounded(source_text: str, item: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if not source_text:
        return True
    return source_contains_any(source_text, [
        candidate.get("proposed_title"),
        candidate.get("description"),
        candidate.get("evidence"),
        item.get("canonical_title"),
        item.get("new_information"),
        item.get("evidence"),
    ])


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
    by_id, by_title = registry_indexes(registry)

    known_mentions = []
    salvaged_candidates = []
    for item in cleaned["known_lore_mentions"]:
        try:
            lore_item_id = int(item.get("lore_item_id"))
        except (TypeError, ValueError):
            warnings.append(f"Dropped known lore mention with invalid lore_item_id: {item.get('canonical_title')}")
            continue
        registry_row = by_id.get(lore_item_id)
        if not registry_row:
            candidate = known_mention_to_candidate(item, session_name)
            if candidate["proposed_title"] and known_mention_is_source_grounded(source_text, item, candidate):
                salvaged_candidates.append(candidate)
                warnings.append(f"Converted unknown known lore mention to new candidate: {candidate['proposed_title']}")
                continue
            warnings.append(f"Dropped known lore mention with unknown lore_item_id {lore_item_id}: {item.get('canonical_title')}")
            continue
        if not canonical_matches_registry(item, registry_row):
            candidate = known_mention_to_candidate(item, session_name)
            if candidate["proposed_title"] and known_mention_is_source_grounded(source_text, item, candidate):
                salvaged_candidates.append(candidate)
                warnings.append(f"Converted mismatched known lore mention to new candidate: {candidate['proposed_title']}")
                continue
            warnings.append(
                f"Dropped known lore mention whose canonical title does not match lore_item_id {lore_item_id}: "
                f"{item.get('canonical_title')} != {registry_row.get('title')}"
            )
            continue
        if source_text and not source_contains_any(source_text, [registry_row.get("title"), item.get("canonical_title")]):
            warnings.append(f"Dropped known lore mention not present in session source: {registry_row.get('title')}")
            continue
        item["canonical_title"] = registry_row.get("title")
        if neutralize_interpretive_update(
            item,
            source_text,
            name_fields=["canonical_title"],
            context_fields=["new_information", "evidence"],
        ):
            item["is_confirmed"] = False
            warnings.append(f"Neutralized party-interpretation lore update: {registry_row.get('title')}")
        elif neutralize_party_framed_update(
            item,
            source_text,
            name_fields=["canonical_title"],
            context_fields=["new_information", "evidence"],
        ):
            item["is_confirmed"] = False
            warnings.append(f"Neutralized party-framed lore update: {registry_row.get('title')}")
        known_mentions.append(item)

    cleaned["known_lore_mentions"] = known_mentions
    known_ids = existing_known_lore_ids(cleaned)
    new_candidates = []
    seen_new_titles = set()
    for candidate in [*salvaged_candidates, *cleaned["new_lore_candidates"]]:
        proposed_title = candidate.get("proposed_title", "")
        if looks_like_party_interpretation(
            candidate,
            source_text,
            name_fields=["proposed_title"],
            context_fields=["description", "evidence"],
        ) or looks_like_unconfirmed_party_framing(
            candidate,
            source_text,
            name_fields=["proposed_title"],
            context_fields=["description", "source_npc", "evidence"],
        ):
            reject_candidate(
                cleaned,
                candidate,
                "Appears to be a party joke, misunderstanding, or theory rather than confirmed lore.",
            )
            warnings.append(f"Rejected party-interpretation lore candidate: {rejection_text(candidate, 'proposed_title')}")
            continue
        registry_row = by_title.get(normalized_name(proposed_title))

        if registry_row:
            registry_id = int(registry_row["id"])
            if registry_id not in known_ids:
                if source_text and not source_contains_any(source_text, [proposed_title, registry_row.get("title")]):
                    reject_candidate(cleaned, candidate, f"Existing lore candidate not present in session source: {registry_row.get('title')}.")
                    warnings.append(f"Rejected existing lore candidate not present in source: {proposed_title}")
                else:
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

        normalized_title = normalized_name(proposed_title)
        if normalized_title in seen_new_titles:
            reject_candidate(cleaned, candidate, f"Duplicate new lore candidate: {proposed_title}.")
            warnings.append(f"Rejected duplicate new lore candidate: {proposed_title}")
            continue
        seen_new_titles.add(normalized_title)
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
            selected = [item for item in selected if item[0] in {"draft_summary", "curated_packet", "diary"}]
        else:
            selected = selected[:2]
    else:
        known = dict(source_candidates(session_name))
        if source not in known:
            raise ValueError(f"Unsupported lore item extraction source: {source}")
        selected = [(source, known[source])]

    return [{"label": label, "path": str(path), "text": clean_source_text(label, read_text(path))} for label, path in selected]


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
    source_sets = chunk_source_sets(sources)

    print(f"Extracting lore item candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_documents = []
    registry_rows_sent = []
    for index, source_set in enumerate(source_sets, start=1):
        if len(source_sets) > 1:
            print(f"  Lore transcript chunk {index}/{len(source_sets)}...")
        chunk_text = "\n\n".join(item["text"] for item in source_set)
        prompt_registry = compact_registry_for_chunk(
            chunk_text,
            registry,
            identity_fields=["title"],
            keep_fields=["id", "title", "category", "source_npc", "is_confirmed"],
        ) if len(source_sets) > 1 else registry
        prompt_npcs = compact_name_list_for_chunk(chunk_text, npcs) if len(source_sets) > 1 else npcs
        prompt_locations = compact_name_list_for_chunk(chunk_text, locations) if len(source_sets) > 1 else locations
        prompt_artifacts = compact_name_list_for_chunk(chunk_text, artifacts) if len(source_sets) > 1 else artifacts
        prompt_metadata = compact_campaign_metadata(campaign_metadata) if len(source_sets) > 1 else campaign_metadata
        registry_rows_sent.append(len(prompt_registry))
        prompt = build_prompt(
            session_name,
            source_set,
            prompt_registry,
            prompt_npcs,
            prompt_locations,
            prompt_artifacts,
            prompt_metadata,
        )
        raw_documents.append(extract_json_object(generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)))
    duration = time.monotonic() - started
    source_text = "\n\n".join(source["text"] for source in sources)
    extracted, guardrail_warnings = postprocess_extraction(
        merge_extraction_documents(raw_documents, EXPECTED_TOP_LEVEL_KEYS),
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
        "chunked": len(source_sets) > 1,
        "chunk_count": len(source_sets),
        "registry_rows_sent": registry_rows_sent,
        "avg_registry_rows_sent": round(sum(registry_rows_sent) / len(registry_rows_sent), 2) if registry_rows_sent else 0,
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
