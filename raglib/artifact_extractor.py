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
    merge_extraction_documents,
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
    "known_artifact_mentions",
    "new_artifact_candidates",
    "rejected_candidates",
    "uncertainties",
]
ARTIFACT_ALIASES = {
    "black blade": "acheron blade",
    "black bladed rapier": "acheron blade",
    "black candle lantern": "lantern with black candle",
    "faban s blade": "acheron blade",
    "green flame lantern": "lantern with black candle",
    "lantern of green flame": "lantern with black candle",
    "orb fragments": "orb of control fragments",
    "fragments of the broken orb": "orb of control fragments",
    "broken orb fragments": "orb of control fragments",
    "trinket from the soil": "trinket",
}
ARTIFACT_STOPWORDS = {
    "a",
    "an",
    "and",
    "from",
    "in",
    "of",
    "the",
    "with",
}


def session_number(session_name: str) -> int:
    match = re.search(r"(\d+)$", session_name)
    if not match:
        raise ValueError(f"Could not parse session number from {session_name!r}")
    return int(match.group(1))


def output_path(session_name: str) -> Path:
    return OUTPUT_DIR / f"{session_name}_artifacts.json"


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
    normalized = re.sub(r"\b([a-z]+) s\b", r"\1", normalized)
    for alias, canonical in ARTIFACT_ALIASES.items():
        normalized = re.sub(rf"\b{re.escape(alias)}\b", canonical, normalized)
    return ARTIFACT_ALIASES.get(normalized, normalized)


def source_contains_any(source_text: str, values: list[Any]) -> bool:
    source = normalized_name(source_text)
    return any(value and normalized_name(value) in source for value in values)


def meaningful_tokens(value: Any) -> list[str]:
    tokens = normalized_name(value).split()
    return [token for token in tokens if token not in ARTIFACT_STOPWORDS and len(token) > 2]


def source_contains_token_set(source_text: str, value: Any) -> bool:
    tokens = meaningful_tokens(value)
    if len(tokens) < 2:
        return False
    source = f" {normalized_name(source_text)} "
    return all(f" {token} " in source for token in tokens)


def source_contains_lantern_paraphrase(source_text: str, value: Any) -> bool:
    tokens = set(meaningful_tokens(value))
    if "lantern" not in tokens:
        return False
    source = normalized_name(source_text)
    return "lantern" in source and ("green flame" in source or "black candle" in source)


def artifact_candidate_source_terms(candidate: dict[str, Any]) -> list[Any]:
    return [
        candidate.get("proposed_name"),
        candidate.get("evidence"),
        candidate.get("description"),
        candidate.get("lore_significance"),
        *(candidate.get("properties") or []),
    ]


def artifact_candidate_is_source_grounded(source_text: str, candidate: dict[str, Any]) -> bool:
    if not source_text:
        return True
    terms = artifact_candidate_source_terms(candidate)
    if source_contains_any(source_text, terms):
        return True
    proposed_name = candidate.get("proposed_name")
    return (
        source_contains_lantern_paraphrase(source_text, proposed_name)
        or source_contains_token_set(source_text, proposed_name)
    )


def rejected_artifact_can_be_salvaged(text: Any) -> bool:
    tokens = set(meaningful_tokens(text))
    return bool(tokens & {"lantern", "trinket"})


def rejected_artifact_to_candidate(item: dict[str, Any], session_name: str) -> dict[str, Any]:
    text = item.get("text") or "Unknown Artifact"
    tokens = set(meaningful_tokens(text))
    artifact_type = "trinket" if "trinket" in tokens else "other"
    return {
        "proposed_name": text,
        "artifact_type": artifact_type,
        "description": f"Recovered from extractor rejection because the item is grounded in the session source: {text}.",
        "lore_significance": "",
        "discovered_session": session_number(session_name),
        "current_holder": "unknown",
        "properties": [],
        "is_sentient": False,
        "is_cursed": False,
        "is_infernal": False,
        "confidence": "medium",
        "evidence": item.get("reason") or "",
    }


def mentioned_as_values(item: dict[str, Any]) -> list[str]:
    values = item.get("mentioned_as", [])
    if isinstance(values, str):
        return [values]
    if isinstance(values, list):
        return [str(value) for value in values if value]
    return []


def known_artifact_source_terms(item: dict[str, Any], registry_row: dict[str, Any]) -> list[Any]:
    terms: list[Any] = [registry_row.get("name"), item.get("canonical_name")]
    registry_name = normalized_name(registry_row.get("name"))
    for value in mentioned_as_values(item):
        if normalized_name(value) == registry_name:
            terms.append(value)
    return terms


def artifact_registry() -> list[dict[str, Any]]:
    registry = []
    for row in canon.artifact_rows():
        registry.append({
            "id": row.get("id"),
            "name": row.get("name") or "",
            "artifact_type": row.get("artifact_type") or "",
            "discovered_session": row.get("discovered_session"),
            "description": row.get("description") or "",
            "lore_significance": row.get("lore_significance") or "",
            "is_sentient": bool(row.get("is_sentient")),
            "is_cursed": bool(row.get("is_cursed")),
            "is_infernal": bool(row.get("is_infernal")),
            "current_holder": row.get("current_holder") or "",
            "notes": row.get("notes") or "",
        })
    return registry


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


def existing_known_artifact_ids(document: dict[str, Any]) -> set[int]:
    ids = set()
    for item in document["known_artifact_mentions"]:
        try:
            ids.add(int(item["artifact_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def candidate_to_known_mention(candidate: dict[str, Any], registry_row: dict[str, Any], session_name: str) -> dict[str, Any]:
    return {
        "artifact_id": registry_row.get("id"),
        "canonical_name": registry_row.get("name"),
        "mentioned_as": [candidate.get("proposed_name")],
        "new_information": candidate.get("description") or "Mentioned in this session; no new canon update proposed.",
        "session_number": session_number(session_name),
        "artifact_type": candidate.get("artifact_type") or registry_row.get("artifact_type") or "",
        "current_holder": candidate.get("current_holder") or registry_row.get("current_holder") or "",
        "properties": candidate.get("properties") or [],
        "is_sentient": bool(candidate.get("is_sentient") or registry_row.get("is_sentient")),
        "is_cursed": bool(candidate.get("is_cursed") or registry_row.get("is_cursed")),
        "is_infernal": bool(candidate.get("is_infernal") or registry_row.get("is_infernal")),
        "confidence": candidate.get("confidence") or "medium",
        "evidence": candidate.get("evidence") or "",
    }


def known_mention_to_candidate(item: dict[str, Any], session_name: str) -> dict[str, Any]:
    name = item.get("canonical_name") or next(iter(mentioned_as_values(item)), "")
    return {
        "proposed_name": name,
        "artifact_type": item.get("artifact_type") or "other",
        "description": item.get("new_information") or "Mentioned as an artifact or important item in this session.",
        "lore_significance": item.get("lore_significance") or "",
        "discovered_session": session_number(session_name),
        "current_holder": item.get("current_holder") or "unknown",
        "properties": item.get("properties") or [],
        "is_sentient": bool(item.get("is_sentient")),
        "is_cursed": bool(item.get("is_cursed")),
        "is_infernal": bool(item.get("is_infernal")),
        "confidence": item.get("confidence") or "medium",
        "evidence": item.get("evidence") or "",
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
    salvaged_candidates = []
    for item in cleaned["known_artifact_mentions"]:
        try:
            artifact_id = int(item.get("artifact_id"))
        except (TypeError, ValueError):
            candidate = known_mention_to_candidate(item, session_name)
            if artifact_candidate_is_source_grounded(source_text, candidate):
                salvaged_candidates.append(candidate)
                warnings.append(f"Converted invalid known artifact mention to new candidate: {candidate['proposed_name']}")
            else:
                warnings.append(f"Dropped known artifact mention with invalid artifact_id: {item.get('canonical_name')}")
            continue
        registry_row = by_id.get(artifact_id)
        if not registry_row:
            candidate = known_mention_to_candidate(item, session_name)
            if artifact_candidate_is_source_grounded(source_text, candidate):
                salvaged_candidates.append(candidate)
                warnings.append(f"Converted unknown known artifact mention to new candidate: {candidate['proposed_name']}")
            else:
                warnings.append(f"Dropped known artifact mention with unknown artifact_id {artifact_id}: {item.get('canonical_name')}")
            continue
        if not canonical_matches_registry(item, registry_row):
            candidate = known_mention_to_candidate(item, session_name)
            if artifact_candidate_is_source_grounded(source_text, candidate):
                salvaged_candidates.append(candidate)
                warnings.append(
                    f"Converted mismatched known artifact mention to new candidate: "
                    f"{candidate['proposed_name']} != {registry_row.get('name')}"
                )
            else:
                warnings.append(
                    f"Dropped known artifact mention whose canonical name does not match artifact_id {artifact_id}: "
                    f"{item.get('canonical_name')} != {registry_row.get('name')}"
                )
            continue
        if source_text and not source_contains_any(source_text, known_artifact_source_terms(item, registry_row)):
            warnings.append(f"Dropped known artifact mention not present in session source: {registry_row.get('name')}")
            continue
        item["canonical_name"] = registry_row.get("name")
        if neutralize_interpretive_update(
            item,
            source_text,
            name_fields=["canonical_name", "mentioned_as"],
            context_fields=["new_information", "evidence"],
        ):
            warnings.append(f"Neutralized party-interpretation artifact update: {registry_row.get('name')}")
        known_mentions.append(item)

    cleaned["known_artifact_mentions"] = known_mentions
    if salvaged_candidates:
        cleaned["new_artifact_candidates"] = [*salvaged_candidates, *cleaned["new_artifact_candidates"]]
    rescued_rejections = []
    remaining_rejections = []
    for item in cleaned["rejected_candidates"]:
        if rejected_artifact_can_be_salvaged(item.get("text")):
            candidate = rejected_artifact_to_candidate(item, session_name)
            if artifact_candidate_is_source_grounded(source_text, candidate):
                rescued_rejections.append(candidate)
                warnings.append(f"Recovered source-grounded rejected artifact candidate: {candidate['proposed_name']}")
                continue
        remaining_rejections.append(item)
    if rescued_rejections:
        cleaned["rejected_candidates"] = remaining_rejections
        cleaned["new_artifact_candidates"] = [*rescued_rejections, *cleaned["new_artifact_candidates"]]
    known_ids = existing_known_artifact_ids(cleaned)
    new_candidates = []
    seen_new_names = set()
    for candidate in cleaned["new_artifact_candidates"]:
        proposed_name = candidate.get("proposed_name", "")
        normalized_proposed = normalized_name(proposed_name)
        if looks_like_party_interpretation(
            candidate,
            source_text,
            name_fields=["proposed_name"],
            context_fields=["description", "lore_significance", "evidence"],
        ):
            reject_candidate(
                cleaned,
                candidate,
                "Appears to be a party joke, misunderstanding, nickname, or theory rather than a confirmed artifact.",
            )
            warnings.append(f"Rejected party-interpretation artifact candidate: {rejection_text(candidate, 'proposed_name')}")
            continue
        if normalized_proposed in seen_new_names:
            reject_candidate(cleaned, candidate, f"Duplicate of new artifact candidate: {proposed_name}.")
            warnings.append(f"Rejected duplicate new artifact candidate: {proposed_name}")
            continue
        seen_new_names.add(normalized_proposed)
        registry_row = by_name.get(normalized_proposed)

        if registry_row:
            registry_id = int(registry_row["id"])
            if registry_id not in known_ids:
                if source_text and not artifact_candidate_is_source_grounded(source_text, candidate):
                    reject_candidate(cleaned, candidate, f"Existing artifact candidate not present in session source: {registry_row.get('name')}.")
                    warnings.append(f"Rejected existing artifact candidate not present in source: {proposed_name}")
                else:
                    cleaned["known_artifact_mentions"].append(candidate_to_known_mention(candidate, registry_row, session_name))
                    known_ids.add(registry_id)
                    warnings.append(f"Moved existing artifact candidate to known mention: {proposed_name}")
            else:
                reject_candidate(cleaned, candidate, f"Duplicate of existing artifact: {registry_row.get('name')}.")
                warnings.append(f"Rejected duplicate existing artifact candidate: {proposed_name}")
            continue

        if source_text and not artifact_candidate_is_source_grounded(source_text, candidate):
            reject_candidate(cleaned, candidate, "Candidate name not found in session source.")
            warnings.append(f"Rejected artifact candidate not present in source: {proposed_name}")
            continue

        new_candidates.append(candidate)

    cleaned["new_artifact_candidates"] = new_candidates
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
            raise ValueError(f"Unsupported artifact extraction source: {source}")
        selected = [(source, known[source])]

    return [{"label": label, "path": str(path), "text": clean_source_text(label, read_text(path))} for label, path in selected]


def build_prompt(
    session_name: str,
    sources: list[dict[str, str]],
    registry: list[dict[str, Any]],
    npcs: list[str],
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
        load_prompt("extract_artifacts").strip(),
        f"Session name: {session_name}",
        f"Session number: {session_number(session_name)}",
        "Campaign metadata JSON:",
        json.dumps(campaign_metadata, indent=2, ensure_ascii=False),
        "Current artifact registry JSON:",
        json.dumps(registry, indent=2, ensure_ascii=False),
        "Current NPC names JSON, for holder/entity disambiguation:",
        json.dumps(npcs, indent=2, ensure_ascii=False),
        "Current location names JSON, for avoiding place/item confusion:",
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


def extract_artifacts(session_name: str, model: Optional[str] = None, source: str = "auto") -> Path:
    model = model or os.environ.get("FARRLIND_ARTIFACT_EXTRACTOR_MODEL", DEFAULT_MODEL)
    sources = load_session_sources(session_name, source)
    campaign_metadata = load_campaign_metadata()
    registry = artifact_registry()
    npcs = [row.get("name") for row in canon.npc_rows() if row.get("name")]
    locations = canon.locations()
    source_sets = chunk_source_sets(sources)

    print(f"Extracting artifact candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_documents = []
    registry_rows_sent = []
    for index, source_set in enumerate(source_sets, start=1):
        if len(source_sets) > 1:
            print(f"  Artifact transcript chunk {index}/{len(source_sets)}...")
        chunk_text = "\n\n".join(item["text"] for item in source_set)
        prompt_registry = compact_registry_for_chunk(
            chunk_text,
            registry,
            identity_fields=["name"],
            keep_fields=["id", "name", "artifact_type", "current_holder"],
        ) if len(source_sets) > 1 else registry
        prompt_npcs = compact_name_list_for_chunk(chunk_text, npcs) if len(source_sets) > 1 else npcs
        prompt_locations = compact_name_list_for_chunk(chunk_text, locations) if len(source_sets) > 1 else locations
        prompt_metadata = compact_campaign_metadata(campaign_metadata) if len(source_sets) > 1 else campaign_metadata
        registry_rows_sent.append(len(prompt_registry))
        prompt = build_prompt(session_name, source_set, prompt_registry, prompt_npcs, prompt_locations, prompt_metadata)
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
        "artifact_registry_count": len(registry),
        "npc_registry_count": len(npcs),
        "location_count": len(locations),
        "duration_seconds": round(duration, 2),
        "guardrail_warning_count": len(guardrail_warnings),
        "guardrail_warnings": guardrail_warnings,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(path),
    }, indent=2) + "\n")
    print(f"Artifact extraction written to: {path}")
    print(f"Artifact extraction metadata written to: {metadata_path}")
    return path
