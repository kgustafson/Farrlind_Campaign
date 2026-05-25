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
    "known_npc_mentions",
    "new_npc_candidates",
    "rejected_candidates",
    "uncertainties",
]
FISHERMEN_TERMS = {
    "fisherman",
    "unnamed fisherman",
    "sun worn fisherman",
    "sun-worn fisherman",
    "one fisherman",
    "the fisherman",
    "fishermen",
    "coastal fishermen",
    "giant fishermen",
}


def session_number(session_name: str) -> int:
    match = re.search(r"(\d+)$", session_name)
    if not match:
        raise ValueError(f"Could not parse session number from {session_name!r}")
    return int(match.group(1))


def output_path(session_name: str) -> Path:
    return OUTPUT_DIR / f"{session_name}_npcs.json"


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


def party_character_names(metadata: dict[str, Any]) -> list[str]:
    names = set()
    for member in metadata.get("party", []) or []:
        for key in ["character_name", "full_name"]:
            if member.get(key):
                names.add(str(member[key]))
        for alias in member.get("aliases", []) or []:
            names.add(str(alias))
    return sorted(names)


def normalized_name(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    tokens = ["reagan" if token == "regan" else "zarovich" if token == "zorovich" else token for token in normalized.split()]
    return " ".join(tokens)


def collapse_repeated_name_tokens(value: Any) -> str:
    normalized = normalized_name(value)
    tokens = normalized.split()
    collapsed: list[str] = []
    index = 0
    while index < len(tokens):
        collapsed.append(tokens[index])
        lookahead = index + 1
        while lookahead < len(tokens) and tokens[lookahead] == tokens[index]:
            lookahead += 1
        index = lookahead
    return " ".join(collapsed)


def registry_indexes(registry: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id = {}
    by_name = {}
    for row in registry:
        if row.get("id") is not None:
            by_id[int(row["id"])] = row
        names = [row.get("name"), row.get("alias")]
        for name in names:
            normalized = normalized_name(name)
            if normalized:
                by_name[normalized] = row
    return by_id, by_name


def is_party_reference(value: Any, party_names: set[str]) -> bool:
    return normalized_name(value) in party_names


def mentioned_as_values(item: dict[str, Any]) -> list[str]:
    values = item.get("mentioned_as", [])
    if isinstance(values, str):
        return [values]
    if isinstance(values, list):
        return [str(value) for value in values if value]
    return []


def canonical_matches_registry(item: dict[str, Any], registry_row: dict[str, Any]) -> bool:
    canonical = collapse_repeated_name_tokens(item.get("canonical_name"))
    valid = {
        collapse_repeated_name_tokens(registry_row.get("name")),
        collapse_repeated_name_tokens(registry_row.get("alias")),
    }
    valid = {name for name in valid if name}
    return canonical in valid or any(name and name in canonical for name in valid)


def source_contains_any(source_text: str, values: list[Any]) -> bool:
    source = normalized_name(source_text)
    return any(value and normalized_name(value) in source for value in values)


def known_mention_source_terms(item: dict[str, Any], registry_row: dict[str, Any]) -> list[Any]:
    return [
        registry_row.get("name"),
        registry_row.get("alias"),
        item.get("canonical_name"),
    ]


def reject_candidate(document: dict[str, Any], candidate: dict[str, Any], reason: str) -> None:
    document["rejected_candidates"].append({
        "text": candidate.get("proposed_name") or candidate.get("text") or "unknown candidate",
        "reason": reason,
    })


def existing_known_npc_ids(document: dict[str, Any]) -> set[int]:
    ids = set()
    for item in document["known_npc_mentions"]:
        try:
            ids.add(int(item["npc_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def candidate_to_known_mention(candidate: dict[str, Any], registry_row: dict[str, Any], session_name: str) -> dict[str, Any]:
    return {
        "npc_id": registry_row.get("id"),
        "canonical_name": registry_row.get("name"),
        "mentioned_as": [candidate.get("proposed_name")],
        "new_information": candidate.get("description") or candidate.get("role") or "Mentioned in this session; no new canon update proposed.",
        "session_number": session_number(session_name),
        "location": candidate.get("first_seen_location") or "",
        "confidence": candidate.get("confidence") or "medium",
        "evidence": candidate.get("evidence") or "",
    }


def metadata_glossary_names(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    names: dict[str, dict[str, Any]] = {}
    for entry in metadata.get("glossary", []) or []:
        term = (entry.get("term") or "").strip()
        if not term or not glossary_entry_is_npc_hint(entry):
            continue
        aliases = [str(alias) for alias in entry.get("aliases", []) or [] if alias]
        detail = {
            "term": term,
            "aliases": aliases,
            "note": entry.get("note") or "",
        }
        for value in [term, *aliases]:
            normalized = normalized_name(value)
            if normalized:
                names[normalized] = detail
    return names


def glossary_entry_is_npc_hint(entry: dict[str, Any]) -> bool:
    text = normalized_name(f"{entry.get('term', '')} {entry.get('note', '')}")
    non_npc_terms = {
        "campaign world",
        "domain",
        "location",
        "place",
        "city",
        "town",
        "village",
        "road",
        "tavern",
        "inn",
        "realm",
        "settlement",
        "party nickname",
    }
    if any(term in text for term in non_npc_terms):
        return False
    npc_terms = {
        "lord",
        "vampire",
        "burgomaster",
        "father",
        "daughter",
        "son",
        "familiar",
        "imp",
        "npc",
        "companion",
        "enemy",
        "ally",
        "mentor",
    }
    return any(term in text for term in npc_terms)


def source_mention_for_item(item: dict[str, Any], metadata_names: dict[str, dict[str, Any]]) -> tuple[str, Optional[dict[str, Any]]]:
    values = [item.get("canonical_name"), *mentioned_as_values(item)]
    for value in values:
        normalized = normalized_name(value)
        if normalized in metadata_names:
            return str(value), metadata_names[normalized]
    for value in values:
        if value:
            return str(value), None
    return "", None


def known_mention_to_candidate(item: dict[str, Any], session_name: str, metadata_entry: Optional[dict[str, Any]]) -> dict[str, Any]:
    proposed_name = (metadata_entry or {}).get("term") or item.get("canonical_name") or next(iter(mentioned_as_values(item)), "")
    return {
        "proposed_name": proposed_name,
        "npc_kind": "named_individual",
        "role": item.get("new_information") or (metadata_entry or {}).get("note") or "Mentioned in this session.",
        "description": (metadata_entry or {}).get("note") or item.get("new_information") or "Mentioned in this session.",
        "first_seen_session": session_number(session_name),
        "first_seen_location": item.get("location") or "",
        "aliases": (metadata_entry or {}).get("aliases") or mentioned_as_values(item),
        "status": "unknown",
        "confidence": item.get("confidence") or "medium",
        "evidence": item.get("evidence") or "",
    }


def metadata_entry_to_candidate(entry: dict[str, Any], session_name: str, source_text: str) -> dict[str, Any]:
    term = entry["term"]
    aliases = entry.get("aliases") or []
    mentioned = next((value for value in [term, *aliases] if source_contains_any(source_text, [value])), term)
    return {
        "proposed_name": term,
        "npc_kind": "named_individual",
        "role": entry.get("note") or "Mentioned in this session.",
        "description": entry.get("note") or "Mentioned in this session.",
        "first_seen_session": session_number(session_name),
        "first_seen_location": "",
        "aliases": aliases,
        "status": "unknown",
        "confidence": "medium",
        "evidence": f"Source mentions {mentioned}.",
    }


def add_glossary_candidates(
    candidates: list[dict[str, Any]],
    metadata_names: dict[str, dict[str, Any]],
    registry_by_name: dict[str, dict[str, Any]],
    party_names: set[str],
    session_name: str,
    source_text: str,
) -> list[dict[str, Any]]:
    seen = {normalized_name(candidate.get("proposed_name")) for candidate in candidates}
    added: list[dict[str, Any]] = []
    unique_entries: dict[str, dict[str, Any]] = {}
    for entry in metadata_names.values():
        unique_entries[normalized_name(entry["term"])] = entry
    for entry in unique_entries.values():
        names = [entry["term"], *(entry.get("aliases") or [])]
        normalized_term = normalized_name(entry["term"])
        if normalized_term in seen or normalized_term in party_names or normalized_term in registry_by_name:
            continue
        if any(normalized_name(alias) in party_names for alias in names):
            continue
        if source_text and not source_contains_any(source_text, names):
            continue
        added.append(metadata_entry_to_candidate(entry, session_name, source_text))
        seen.add(normalized_term)
    return [*candidates, *added]


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = normalized_name(candidate.get("proposed_name"))
        if not key or key in seen:
            continue
        deduped.append(candidate)
        seen.add(key)
    return deduped


def remove_rejections_for_accepted_candidates(document: dict[str, Any]) -> None:
    accepted = {normalized_name(candidate.get("proposed_name")) for candidate in document["new_npc_candidates"]}
    accepted = {item for item in accepted if item}
    document["rejected_candidates"] = [
        item for item in document["rejected_candidates"]
        if normalized_name(item.get("text")) not in accepted
    ]


def postprocess_extraction(
    document: dict[str, Any],
    registry: list[dict[str, Any]],
    campaign_metadata: dict[str, Any],
    session_name: str,
    source_text: str = "",
) -> tuple[dict[str, Any], list[str]]:
    cleaned = normalize_extraction(document)
    warnings = []
    party_names = {normalized_name(name) for name in party_character_names(campaign_metadata)}
    metadata_names = metadata_glossary_names(campaign_metadata)
    by_id, by_name = registry_indexes(registry)

    known_mentions = []
    recovered_candidates = []
    for item in cleaned["known_npc_mentions"]:
        if any(is_party_reference(value, party_names) for value in [item.get("canonical_name"), *mentioned_as_values(item)]):
            warnings.append(f"Dropped known mention mapped from party member: {item.get('mentioned_as')}")
            continue
        mention_value, metadata_entry = source_mention_for_item(item, metadata_names)
        try:
            npc_id = int(item.get("npc_id"))
        except (TypeError, ValueError):
            if mention_value and (not source_text or source_contains_any(source_text, [mention_value])):
                recovered_candidates.append(known_mention_to_candidate(item, session_name, metadata_entry))
                warnings.append(f"Recovered invalid-id known mention as new NPC candidate: {item.get('canonical_name')}")
            else:
                warnings.append(f"Dropped known mention with invalid npc_id: {item.get('canonical_name')}")
            continue
        registry_row = by_id.get(npc_id)
        if not registry_row:
            if mention_value and (not source_text or source_contains_any(source_text, [mention_value])):
                recovered_candidates.append(known_mention_to_candidate(item, session_name, metadata_entry))
                warnings.append(f"Recovered unknown-id known mention as new NPC candidate: {item.get('canonical_name')}")
            else:
                warnings.append(f"Dropped known mention with unknown npc_id {npc_id}: {item.get('canonical_name')}")
            continue
        if not canonical_matches_registry(item, registry_row):
            if mention_value and (not source_text or source_contains_any(source_text, [mention_value])):
                recovered_candidates.append(known_mention_to_candidate(item, session_name, metadata_entry))
                warnings.append(
                    f"Recovered mismatched-id known mention as new NPC candidate: "
                    f"{item.get('canonical_name')} != {registry_row.get('name')}"
                )
                continue
            warnings.append(
                f"Dropped known mention whose canonical name does not match npc_id {npc_id}: "
                f"{item.get('canonical_name')} != {registry_row.get('name')}"
            )
            continue
        if source_text and not source_contains_any(source_text, known_mention_source_terms(item, registry_row)):
            warnings.append(f"Dropped known mention not present in session source: {registry_row.get('name')}")
            continue
        item["canonical_name"] = registry_row.get("name")
        if neutralize_interpretive_update(
            item,
            source_text,
            name_fields=["canonical_name", "mentioned_as"],
            context_fields=["new_information", "evidence"],
        ):
            warnings.append(f"Neutralized party-interpretation NPC update: {registry_row.get('name')}")
        elif neutralize_party_framed_update(
            item,
            source_text,
            name_fields=["canonical_name", "mentioned_as"],
            context_fields=["new_information", "evidence"],
        ):
            warnings.append(f"Neutralized party-framed NPC update: {registry_row.get('name')}")
        known_mentions.append(item)

    cleaned["known_npc_mentions"] = known_mentions
    known_ids = existing_known_npc_ids(cleaned)
    new_candidates = []
    for candidate in [*recovered_candidates, *cleaned["new_npc_candidates"]]:
        proposed_name = candidate.get("proposed_name", "")
        normalized_proposed = normalized_name(proposed_name)
        registry_row = by_name.get(normalized_proposed)
        if not registry_row and normalized_proposed in FISHERMEN_TERMS:
            registry_row = by_name.get("giant fishermen")
        party_framed = looks_like_party_interpretation(
            candidate,
            source_text,
            name_fields=["proposed_name"],
            context_fields=["role", "description", "evidence"],
        ) or looks_like_unconfirmed_party_framing(
            candidate,
            source_text,
            name_fields=["proposed_name"],
            context_fields=["role", "description", "evidence"],
        )
        if party_framed and not registry_row:
            reject_candidate(
                cleaned,
                candidate,
                "Appears to be a party joke, nickname, misunderstanding, or theory rather than a confirmed NPC.",
            )
            warnings.append(f"Rejected party-interpretation NPC candidate: {rejection_text(candidate, 'proposed_name')}")
            continue
        if "burger master" in normalized_proposed:
            reject_candidate(
                cleaned,
                candidate,
                "Appears to be a party joke, nickname, misunderstanding, or theory rather than a confirmed NPC.",
            )
            warnings.append(f"Rejected Burger Master NPC candidate: {proposed_name}")
            continue
        if is_party_reference(proposed_name, party_names):
            reject_candidate(cleaned, candidate, "Party member; not an NPC candidate.")
            warnings.append(f"Rejected party member candidate: {proposed_name}")
            continue

        if "representative of the giant fishermen" in normalized_name(candidate.get("role")):
            reject_candidate(cleaned, candidate, "Representative of existing Giant fishermen group.")
            warnings.append(f"Rejected representative group candidate: {proposed_name}")
            continue

        if registry_row:
            registry_id = int(registry_row["id"])
            if registry_id not in known_ids:
                if source_text and not source_contains_any(source_text, [proposed_name, registry_row.get("name"), registry_row.get("alias")]):
                    reject_candidate(cleaned, candidate, f"Existing NPC candidate not present in session source: {registry_row.get('name')}.")
                    warnings.append(f"Rejected existing NPC candidate not present in source: {proposed_name}")
                else:
                    mention = candidate_to_known_mention(candidate, registry_row, session_name)
                    if party_framed:
                        mention["new_information"] = "Mentioned in this session; no new canon update proposed."
                        warnings.append(f"Neutralized party-framed NPC candidate update: {registry_row.get('name')}")
                    cleaned["known_npc_mentions"].append(mention)
                    known_ids.add(registry_id)
                    warnings.append(f"Moved existing NPC candidate to known mention: {proposed_name}")
            else:
                reject_candidate(cleaned, candidate, f"Duplicate of existing NPC: {registry_row.get('name')}.")
                warnings.append(f"Rejected duplicate existing NPC candidate: {proposed_name}")
            continue

        if source_text and not source_contains_any(source_text, [proposed_name, *(candidate.get("aliases") or [])]):
            reject_candidate(cleaned, candidate, "Candidate name not found in session source.")
            warnings.append(f"Rejected NPC candidate not present in source: {proposed_name}")
            continue

        new_candidates.append(candidate)

    cleaned["new_npc_candidates"] = dedupe_candidates(add_glossary_candidates(
        new_candidates,
        metadata_names,
        by_name,
        party_names,
        session_name,
        source_text,
    ))
    remove_rejections_for_accepted_candidates(cleaned)
    return cleaned, warnings


def load_session_sources(session_name: str, source: str = "auto") -> list[dict[str, str]]:
    selected: list[tuple[str, Path]]
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
            raise ValueError(f"Unsupported NPC extraction source: {source}")
        selected = [(source, known[source])]

    sources = []
    for label, path in selected:
        text = clean_source_text(label, read_text(path))
        sources.append({
            "label": label,
            "path": str(path),
            "text": text,
        })
    return sources


def npc_registry() -> list[dict[str, Any]]:
    rows = canon.npc_rows()
    registry = []
    for row in rows:
        registry.append({
            "id": row.get("id"),
            "name": row.get("name") or "",
            "alias": row.get("alias") or "",
            "faction": row.get("faction") or "",
            "status": row.get("status") or "",
            "last_known_location": row.get("last_known_location") or "",
            "first_seen_session": row.get("first_seen_session"),
            "description": row.get("description") or "",
            "is_named": bool(row.get("is_named")),
            "notes": row.get("notes") or "",
        })
    return registry


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
        load_prompt("extract_npcs").strip(),
        f"Session name: {session_name}",
        f"Session number: {session_number(session_name)}",
        "Campaign metadata JSON:",
        json.dumps(campaign_metadata, indent=2, ensure_ascii=False),
        "Party character names that must not be extracted as NPCs JSON:",
        json.dumps(party_character_names(campaign_metadata), indent=2, ensure_ascii=False),
        "Current NPC registry JSON:",
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


def normalize_extraction(document: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key in EXPECTED_TOP_LEVEL_KEYS:
        value = document.get(key, [])
        normalized[key] = value if isinstance(value, list) else []
    return normalized


def extract_npcs(session_name: str, model: Optional[str] = None, source: str = "auto") -> Path:
    model = model or os.environ.get("FARRLIND_NPC_EXTRACTOR_MODEL", DEFAULT_MODEL)
    sources = load_session_sources(session_name, source)
    campaign_metadata = load_campaign_metadata()
    registry = npc_registry()
    locations = canon.locations()
    source_sets = chunk_source_sets(sources)

    print(f"Extracting NPC candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_documents = []
    registry_rows_sent = []
    for index, source_set in enumerate(source_sets, start=1):
        if len(source_sets) > 1:
            print(f"  NPC transcript chunk {index}/{len(source_sets)}...")
        chunk_text = "\n\n".join(item["text"] for item in source_set)
        prompt_registry = compact_registry_for_chunk(
            chunk_text,
            registry,
            identity_fields=["name", "alias"],
            keep_fields=["id", "name", "alias", "status", "is_named"],
        ) if len(source_sets) > 1 else registry
        prompt_locations = compact_name_list_for_chunk(chunk_text, locations) if len(source_sets) > 1 else locations
        prompt_metadata = compact_campaign_metadata(campaign_metadata) if len(source_sets) > 1 else campaign_metadata
        registry_rows_sent.append(len(prompt_registry))
        prompt = build_prompt(session_name, source_set, prompt_registry, prompt_locations, prompt_metadata)
        raw_documents.append(extract_json_object(generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)))
    duration = time.monotonic() - started
    source_text = "\n\n".join(source["text"] for source in sources)
    extracted, guardrail_warnings = postprocess_extraction(
        merge_extraction_documents(raw_documents, EXPECTED_TOP_LEVEL_KEYS),
        registry,
        campaign_metadata,
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
        "party_character_names": party_character_names(campaign_metadata),
        "npc_registry_count": len(registry),
        "location_count": len(locations),
        "duration_seconds": round(duration, 2),
        "guardrail_warning_count": len(guardrail_warnings),
        "guardrail_warnings": guardrail_warnings,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(path),
    }, indent=2) + "\n")
    print(f"NPC extraction written to: {path}")
    print(f"NPC extraction metadata written to: {metadata_path}")
    return path
