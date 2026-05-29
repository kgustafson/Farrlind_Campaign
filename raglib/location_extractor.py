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
    tokens = [
        "zarovich" if token in {"zarkovich", "zorovich"} else token
        for token in normalized.split()
    ]
    normalized = " ".join(tokens)
    for alias, canonical in LOCATION_ALIASES.items():
        normalized = re.sub(rf"\b{re.escape(alias)}\b", canonical, normalized)
    return LOCATION_ALIASES.get(normalized, normalized)


def normalized_display_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\bZarkovich\b", "Zarovich", text, flags=re.IGNORECASE)
    text = re.sub(r"\bZorovich\b", "Zarovich", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(Strahd\s+von\s+Zarovich)\s+von\s+Zarovich\b",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if normalized_name(text) == "strahd von zarovich s mansion":
        return "Strahd von Zarovich's Mansion"
    return text


def source_contains_any(source_text: str, values: list[Any]) -> bool:
    source = normalized_name(source_text)
    return any(value and normalized_name(value) in source for value in values)


def confirmed_place_in_source(candidate: dict[str, Any], source_text: str) -> bool:
    name = str(candidate.get("proposed_name") or "").strip()
    if not name or not source_text:
        return False
    normalized_source = normalized_name(source_text)
    normalized_candidate = normalized_name(name)
    type_text = normalized_name(candidate.get("location_type") or "")
    description = normalized_name(candidate.get("description") or "")
    place_types = {
        "tavern",
        "inn",
        "building",
        "road",
        "town",
        "village",
        "settlement",
        "district",
        "landmark",
        "mansion",
        "castle",
    }
    if not any(place_type in {type_text} or place_type in description for place_type in place_types):
        return False
    if (
        "mansion" in normalized_candidate
        and "mansion" in normalized_source
        and any(term in normalized_source for term in ["strahd", "zarovich", "ismark", "marina"])
    ):
        return True
    confirmation_patterns = [
        f"named {normalized_candidate}",
        f"called {normalized_candidate}",
        f"the {type_text} {normalized_candidate}" if type_text else "",
        f"{type_text} named {normalized_candidate}" if type_text else "",
    ]
    return any(pattern and pattern in normalized_source for pattern in confirmation_patterns)


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


def known_mention_to_candidate(item: dict[str, Any], session_name: str) -> dict[str, Any]:
    name = item.get("canonical_name") or next(iter(mentioned_as_values(item)), "")
    return {
        "proposed_name": name,
        "location_type": item.get("location_type") or "other",
        "description": item.get("new_information") or "Mentioned as a location in this session.",
        "first_visited_session": session_number(session_name),
        "parent_location": item.get("parent_location") or "",
        "is_underwater": bool(item.get("is_underwater")),
        "is_feywild": bool(item.get("is_feywild")),
        "confidence": item.get("confidence") or "medium",
        "evidence": item.get("evidence") or "",
    }


def confirmed_named_place_candidates(source_text: str, session_name: str) -> list[dict[str, Any]]:
    candidates = []
    named_pattern = re.compile(
        r"\b(?P<type>tavern|inn|road|village|town|mansion|castle|manor|house)\s+named\s+"
        r"(?P<name>[A-Z][A-Za-z' -]+?)(?:,|\.|\n| where| with|$)",
        flags=re.IGNORECASE,
    )
    for match in named_pattern.finditer(source_text):
        name = match.group("name").strip()
        location_type = match.group("type").lower()
        if not name:
            continue
        candidates.append({
            "proposed_name": name,
            "location_type": location_type,
            "description": f"A {location_type} named {name}.",
            "first_visited_session": session_number(session_name),
            "parent_location": "",
            "is_underwater": False,
            "is_feywild": False,
            "confidence": "high",
            "evidence": f"Source names a {location_type}: {name}.",
        })
    village_sign_pattern = re.compile(
        r"\bwelcome to the (?P<type>village|town|city) of (?P<name>[A-Z][A-Za-z' -]+?)(?:,|\.|\n| the |$)",
        flags=re.IGNORECASE,
    )
    for match in village_sign_pattern.finditer(source_text):
        place = match.group("name").strip().title()
        location_type = match.group("type").lower()
        if not place:
            continue
        name = f"{location_type.title()} of {place}"
        candidates.append({
            "proposed_name": name,
            "location_type": location_type,
            "description": f"A {location_type} marked by a welcome sign.",
            "first_visited_session": session_number(session_name),
            "parent_location": place,
            "is_underwater": False,
            "is_feywild": False,
            "confidence": "high",
            "evidence": f"Source sign reads welcome to the {location_type} of {place}.",
        })
    return candidates


def normalize_candidate_details(candidate: dict[str, Any], source_text: str) -> dict[str, Any]:
    proposed_name = str(candidate.get("proposed_name") or "").strip()
    if not proposed_name:
        return candidate
    proposed_name = normalized_display_name(proposed_name)
    candidate["proposed_name"] = proposed_name
    if candidate.get("parent_location"):
        candidate["parent_location"] = normalized_display_name(candidate.get("parent_location"))
    normalized_source = normalized_name(source_text)
    normalized_proposed = normalized_name(proposed_name)
    if normalized_proposed == "strahd von zarovich s mansion" and "mansion" in normalized_source:
        candidate["location_type"] = "mansion"
        if not candidate.get("description") or looks_like_party_interpretation(
            candidate,
            source_text,
            name_fields=["proposed_name"],
            context_fields=["description", "evidence"],
        ):
            candidate["description"] = "A mansion reached from Blood on the Vine, down a lane north past the town square."
        if "village of barovia" in normalized_source:
            candidate["parent_location"] = "Village of Barovia"
        elif not candidate.get("parent_location") or "strahd" in normalized_name(candidate.get("parent_location")):
            candidate["parent_location"] = "Barovia"
    if f"tavern named {normalized_proposed}" in normalized_source:
        candidate["location_type"] = "tavern"
        description_text = normalized_name(candidate.get("description"))
        if (
            not candidate.get("description")
            or "settlement" in description_text
            or "vegan" in description_text
        ):
            candidate["description"] = f"A tavern named {proposed_name}."
    if normalized_proposed == "blood on the vine" and "village of barovia" in normalized_source:
        candidate["parent_location"] = "Village of Barovia"
    return candidate


def postprocess_source_text(session_name: str, sources: list[dict[str, str]]) -> str:
    texts = [source["text"] for source in sources]
    raw_transcript = RAW / f"{session_name}_transcript.txt"
    if raw_transcript.exists() and not any(source["label"] == "transcript" for source in sources):
        texts.append(clean_source_text("transcript", read_text(raw_transcript)))
    return "\n\n".join(texts)


def current_play_source_text(session_name: str) -> str:
    raw_transcript = RAW / f"{session_name}_transcript.txt"
    if not raw_transcript.exists():
        return ""
    return clean_source_text("transcript", read_text(raw_transcript))


def dedupe_location_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    seen = set()
    for candidate in candidates:
        key = normalized_name(candidate.get("proposed_name"))
        if not key or key in seen:
            continue
        deduped.append(candidate)
        seen.add(key)
    return deduped


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
    current_source_text: str = "",
) -> tuple[dict[str, Any], list[str]]:
    cleaned = normalize_extraction(document)
    warnings = []
    by_id, by_name = registry_indexes(registry)

    known_mentions = []
    salvaged_candidates = []
    for item in cleaned["known_location_mentions"]:
        try:
            location_id = int(item.get("location_id"))
        except (TypeError, ValueError):
            candidate = known_mention_to_candidate(item, session_name)
            if source_text and candidate["proposed_name"] and source_contains_any(source_text, [candidate["proposed_name"]]):
                salvaged_candidates.append(candidate)
                warnings.append(f"Converted invalid known location mention to new candidate: {candidate['proposed_name']}")
            else:
                warnings.append(f"Dropped known location mention with invalid location_id: {item.get('canonical_name')}")
            continue
        registry_row = by_id.get(location_id)
        if not registry_row:
            candidate = known_mention_to_candidate(item, session_name)
            if source_text and candidate["proposed_name"] and source_contains_any(source_text, [candidate["proposed_name"]]):
                salvaged_candidates.append(candidate)
                warnings.append(f"Converted unknown known location mention to new candidate: {candidate['proposed_name']}")
            else:
                warnings.append(f"Dropped known location mention with unknown location_id {location_id}: {item.get('canonical_name')}")
            continue
        if not canonical_matches_registry(item, registry_row):
            candidate = known_mention_to_candidate(item, session_name)
            if source_text and candidate["proposed_name"] and source_contains_any(source_text, [candidate["proposed_name"]]):
                salvaged_candidates.append(candidate)
                warnings.append(
                    f"Converted mismatched known location mention to new candidate: "
                    f"{candidate['proposed_name']} != {registry_row.get('name')}"
                )
            else:
                warnings.append(
                    f"Dropped known location mention whose canonical name does not match location_id {location_id}: "
                    f"{item.get('canonical_name')} != {registry_row.get('name')}"
                )
            continue
        if source_text and not source_contains_any(source_text, [registry_row.get("name"), item.get("canonical_name")]):
            warnings.append(f"Dropped known location mention not present in session source: {registry_row.get('name')}")
            continue
        try:
            first_seen = int(registry_row.get("first_visited_session") or 0)
        except (TypeError, ValueError):
            first_seen = 0
        if (
            current_source_text
            and first_seen
            and first_seen < session_number(session_name)
            and not source_contains_any(current_source_text, [registry_row.get("name"), item.get("canonical_name")])
        ):
            warnings.append(f"Dropped prior-session location mention not present after recap: {registry_row.get('name')}")
            continue
        item["canonical_name"] = registry_row.get("name")
        if neutralize_interpretive_update(
            item,
            source_text,
            name_fields=["canonical_name", "mentioned_as"],
            context_fields=["new_information", "evidence"],
        ):
            warnings.append(f"Neutralized party-interpretation location update: {registry_row.get('name')}")
        known_mentions.append(item)

    cleaned["known_location_mentions"] = known_mentions
    if source_text:
        salvaged_candidates = [*salvaged_candidates, *confirmed_named_place_candidates(source_text, session_name)]
    if salvaged_candidates:
        cleaned["new_location_candidates"] = dedupe_location_candidates([*salvaged_candidates, *cleaned["new_location_candidates"]])
    known_ids = existing_known_location_ids(cleaned)
    new_candidates = []
    seen_new_names = set()
    for candidate in cleaned["new_location_candidates"]:
        candidate = normalize_candidate_details(candidate, source_text)
        proposed_name = candidate.get("proposed_name", "")
        normalized_proposed = normalized_name(proposed_name)
        confirmed_place = confirmed_place_in_source(candidate, source_text)
        if not confirmed_place and looks_like_party_interpretation(
            candidate,
            source_text,
            name_fields=["proposed_name"],
            context_fields=["description", "evidence"],
        ):
            reject_candidate(
                cleaned,
                candidate,
                "Appears to be a party joke, misunderstanding, nickname, or theory rather than a confirmed location.",
            )
            warnings.append(f"Rejected party-interpretation location candidate: {rejection_text(candidate, 'proposed_name')}")
            continue
        if normalized_proposed in seen_new_names:
            reject_candidate(cleaned, candidate, f"Duplicate of new location candidate: {proposed_name}.")
            warnings.append(f"Rejected duplicate new location candidate: {proposed_name}")
            continue
        seen_new_names.add(normalized_proposed)
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

        if source_text and not confirmed_place and not source_contains_any(source_text, [proposed_name]):
            reject_candidate(cleaned, candidate, "Candidate name not found in session source.")
            warnings.append(f"Rejected location candidate not present in source: {proposed_name}")
            continue

        new_candidates.append(candidate)

    cleaned["new_location_candidates"] = dedupe_location_candidates(new_candidates)
    accepted = {normalized_name(candidate.get("proposed_name")) for candidate in new_candidates}
    cleaned["rejected_candidates"] = [
        item for item in cleaned["rejected_candidates"]
        if normalized_name(item.get("text")) not in accepted
    ]
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
            raise ValueError(f"Unsupported location extraction source: {source}")
        selected = [(source, known[source])]

    sources = []
    for label, path in selected:
        sources.append({
            "label": label,
            "path": str(path),
            "text": clean_source_text(label, read_text(path)),
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
    source_sets = chunk_source_sets(sources)

    print(f"Extracting location candidates for {session_name} with {model}...")
    started = time.monotonic()
    raw_documents = []
    registry_rows_sent = []
    for index, source_set in enumerate(source_sets, start=1):
        if len(source_sets) > 1:
            print(f"  Location transcript chunk {index}/{len(source_sets)}...")
        chunk_text = "\n\n".join(item["text"] for item in source_set)
        prompt_registry = compact_registry_for_chunk(
            chunk_text,
            registry,
            identity_fields=["name"],
            keep_fields=["id", "name", "location_type", "parent_location"],
        ) if len(source_sets) > 1 else registry
        prompt_npcs = compact_name_list_for_chunk(chunk_text, npcs) if len(source_sets) > 1 else npcs
        prompt_metadata = compact_campaign_metadata(campaign_metadata) if len(source_sets) > 1 else campaign_metadata
        registry_rows_sent.append(len(prompt_registry))
        prompt = build_prompt(session_name, source_set, prompt_registry, prompt_npcs, prompt_metadata)
        raw_documents.append(extract_json_object(generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)))
    duration = time.monotonic() - started
    source_text = postprocess_source_text(session_name, sources)
    current_source = current_play_source_text(session_name)
    extracted, guardrail_warnings = postprocess_extraction(
        merge_extraction_documents(raw_documents, EXPECTED_TOP_LEVEL_KEYS),
        registry,
        session_name,
        source_text,
        current_source,
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
