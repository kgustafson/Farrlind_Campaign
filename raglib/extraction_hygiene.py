import re
from typing import Any

from raglib.chunking import chunk_text


PARTY_INTERPRETATION_MARKERS = {
    "assume",
    "assumes",
    "believe",
    "believes",
    "bit",
    "called",
    "call",
    "calls",
    "confuse",
    "confuses",
    "interprets",
    "interpreting",
    "joke",
    "jokingly",
    "jokes",
    "misheard",
    "misinterpret",
    "misinterprets",
    "misread",
    "misreads",
    "mistaken",
    "mistakenly",
    "nickname",
    "nicknamed",
    "pun",
    "sarcasm",
    "sarcastic",
    "thinks",
}

WORLD_FACT_MARKERS = {
    "letter says",
    "npc says",
    "narrator says",
    "revealed by",
    "source confirms",
}


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def compact_candidate_text(candidate: dict[str, Any], fields: list[str]) -> str:
    parts: list[str] = []
    for field in fields:
        value = candidate.get(field)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item)
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def split_aliases(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [
        part.strip()
        for part in re.split(r"[;,|]", str(value or ""))
        if part.strip()
    ]


def row_identity_terms(row: dict[str, Any], fields: list[str]) -> list[str]:
    terms = []
    for field in fields:
        value = row.get(field)
        if field in {"alias", "aliases"}:
            terms.extend(split_aliases(value))
        elif value:
            terms.append(str(value))
    return terms


def text_contains_term(source_text: str, term: str) -> bool:
    normalized_source = f" {normalized_text(source_text)} "
    normalized_term = normalized_text(term)
    return bool(normalized_term) and f" {normalized_term} " in normalized_source


def compact_row(row: dict[str, Any], keep_fields: list[str]) -> dict[str, Any]:
    return {field: row.get(field) for field in keep_fields if row.get(field) not in (None, "", [])}


def compact_registry_for_chunk(
    chunk_text: str,
    registry: list[dict[str, Any]],
    identity_fields: list[str],
    keep_fields: list[str],
    max_rows: int = 40,
) -> list[dict[str, Any]]:
    matches = []
    seen = set()
    for row in registry:
        terms = row_identity_terms(row, identity_fields)
        if not any(text_contains_term(chunk_text, term) for term in terms):
            continue
        key = row.get("id") if row.get("id") is not None else normalized_text("|".join(terms))
        if key in seen:
            continue
        seen.add(key)
        matches.append(compact_row(row, keep_fields))
        if len(matches) >= max_rows:
            break
    return matches


def compact_name_list_for_chunk(chunk_text: str, names: list[str], max_names: int = 80) -> list[str]:
    compacted = []
    seen = set()
    for name in names:
        if not text_contains_term(chunk_text, name):
            continue
        normalized = normalized_text(name)
        if normalized in seen:
            continue
        seen.add(normalized)
        compacted.append(name)
        if len(compacted) >= max_names:
            break
    return compacted


def compact_campaign_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    campaign = metadata.get("campaign") or {}
    dm = metadata.get("dm") or {}
    return {
        "campaign": {
            key: campaign.get(key)
            for key in ["id", "name"]
            if campaign.get(key)
        },
        "dm": {
            key: dm.get(key)
            for key in ["name", "aliases"]
            if dm.get(key)
        },
        "party": [
            {
                key: member.get(key)
                for key in ["character_name", "full_name", "player_name", "aliases"]
                if member.get(key)
            }
            for member in metadata.get("party", []) or []
        ],
        "glossary": [
            {
                key: item.get(key)
                for key in ["term", "aliases"]
                if item.get(key)
            }
            for item in metadata.get("glossary", []) or []
        ],
        "extraction_guidance": metadata.get("extraction_guidance") or {},
    }


def source_windows(source_text: str, phrase: str, radius: int = 220) -> list[str]:
    phrase = str(phrase or "").strip()
    if not source_text or not phrase:
        return []
    windows = []
    pattern = re.compile(re.escape(phrase), flags=re.IGNORECASE)
    for match in pattern.finditer(source_text):
        start = max(0, match.start() - radius)
        end = min(len(source_text), match.end() + radius)
        windows.append(source_text[start:end])
    return windows


def has_any_marker(text: str, markers: set[str]) -> bool:
    normalized = f" {normalized_text(text)} "
    return any(f" {marker} " in normalized for marker in markers)


def looks_like_party_interpretation(
    candidate: dict[str, Any],
    source_text: str,
    name_fields: list[str],
    context_fields: list[str],
) -> bool:
    """Return true for candidates whose evidence appears to be a PC joke/theory.

    This is intentionally campaign-neutral. It does not know any setting names;
    it only catches extraction candidates framed as jokes, misunderstandings,
    nicknames, sarcasm, or party interpretations rather than world facts.
    """
    phrases = [
        str(candidate.get(field) or "").strip()
        for field in name_fields
        if str(candidate.get(field) or "").strip()
    ]
    candidate_text = compact_candidate_text(candidate, [*name_fields, *context_fields])
    contexts = [candidate_text]
    for phrase in phrases:
        contexts.extend(source_windows(source_text, phrase))
    combined = " ".join(contexts)
    if not has_any_marker(combined, PARTY_INTERPRETATION_MARKERS):
        return False
    return not has_any_marker(combined, WORLD_FACT_MARKERS)


def rejection_text(candidate: dict[str, Any], *fields: str) -> str:
    for field in fields:
        value = candidate.get(field)
        if value:
            return str(value)
    return "unknown candidate"


def should_chunk_sources(sources: list[dict[str, str]], max_chars: int = 30000) -> bool:
    return (
        len(sources) == 1
        and sources[0].get("label") == "transcript"
        and len(sources[0].get("text") or "") > max_chars
    )


def chunk_source_sets(sources: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    if not should_chunk_sources(sources):
        return [sources]

    source = sources[0]
    chunks = chunk_text(source.get("text") or "")
    return [[{
        "label": f"transcript_chunk_{index:03d}",
        "path": source.get("path") or "",
        "text": chunk,
    }] for index, chunk in enumerate(chunks, start=1)]


def merge_extraction_documents(
    documents: list[dict[str, Any]],
    expected_keys: list[str],
) -> dict[str, list[Any]]:
    merged: dict[str, list[Any]] = {key: [] for key in expected_keys}
    for document in documents:
        for key in expected_keys:
            value = document.get(key, [])
            if isinstance(value, list):
                merged[key].extend(value)
    return merged


def neutralize_interpretive_update(
    item: dict[str, Any],
    source_text: str,
    name_fields: list[str],
    context_fields: list[str],
    neutral_text: str = "Mentioned in this session; no new canon update proposed.",
) -> bool:
    if not looks_like_party_interpretation(item, source_text, name_fields, context_fields):
        return False
    if "new_information" in item:
        item["new_information"] = neutral_text
    return True
