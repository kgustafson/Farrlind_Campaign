import re
from typing import Any

import yaml

from raglib.config import RAW, CLEAN
from raglib.io_utils import read_text, write_text
from raglib.chunking import chunk_text
from raglib.prompts import load_prompt, build_prompt
from raglib.ollama_client import chat


def transcript_path(session_name: str):
    return RAW / f"{session_name}_transcript.txt"


def curated_path(session_name: str):
    return CLEAN / f"{session_name}_curated.md"


def narrative_path(session_name: str):
    return CLEAN / f"{session_name}_narrative.md"


def spine_path(session_name: str):
    return CLEAN / f"{session_name}_spine.yaml"


def spine_validation_path(session_name: str):
    return CLEAN / f"{session_name}_spine_validation.md"


def events_path(session_name: str):
    return CLEAN / f"{session_name}_events.md"


def optional_section(label: str, path) -> str:
    if not path.exists():
        return ""
    text = read_text(path).strip()
    if not text:
        return ""
    return f"--- {label} START ---\n{text}\n--- {label} END ---"


SECTION_RE = re.compile(r"^## .+$", re.MULTILINE)


def split_markdown_sections(text: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(0).strip()] = text[match.end():end].strip()
    return sections


def narrative_chronology_lines(narrative: str) -> list[str]:
    body = split_markdown_sections(narrative).get("## Chronological Major Events", "")
    return narrative_bullet_lines(body)


def narrative_bullet_lines(body: str) -> list[str]:
    lines = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith(("-", "*")) and "None identified" not in line:
            lines.append(re.sub(r"^[-*]\s*", "", line).strip())
    return [line for line in lines if line]


def load_spine(session_name: str) -> dict[str, Any]:
    if not spine_path(session_name).exists():
        return {}
    data = yaml.safe_load(read_text(spine_path(session_name))) or {}
    return data if isinstance(data, dict) else {}


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


STOP_WORDS = {
    "and",
    "are",
    "from",
    "into",
    "party",
    "that",
    "the",
    "them",
    "they",
    "three",
    "with",
}

REVIEW_EVENT_TYPES = {
    "combat",
    "discovery",
    "downtime",
    "hazard",
    "lore",
    "mystery",
    "social",
    "travel",
}

EVENT_TYPE_ALIASES = {
    "cliffhanger": "social",
    "consequence": "social",
    "roleplay": "social",
    "npc_faction": "social",
    "resource": "discovery",
    "resource_change": "discovery",
    "item": "discovery",
    "acquisition": "discovery",
    "lore_reveal": "lore",
    "character": "social",
    "character_development": "social",
    "quest_objective": "lore",
    "exploration": "travel",
    "environment": "travel",
    "other": "discovery",
    "unclear_verify": "mystery",
}

SECTION_EVENT_TYPE_HINTS = {
    "## Combat / Encounters": "combat",
    "## Items / Loot / Resources": "discovery",
    "## Character Notes": "social",
    "## Open Threads": "mystery",
}

EVENT_VERBS = {
    "arrive",
    "arrives",
    "approach",
    "approaches",
    "attack",
    "attacks",
    "become",
    "becomes",
    "confront",
    "confronts",
    "discover",
    "discovers",
    "eat",
    "eats",
    "enter",
    "enters",
    "find",
    "finds",
    "flee",
    "flees",
    "follow",
    "follows",
    "learn",
    "learns",
    "loot",
    "loots",
    "read",
    "reads",
    "rise",
    "rises",
    "steal",
    "steals",
    "summon",
    "summons",
    "take",
    "takes",
    "travel",
    "travels",
}


def content_words(value: Any) -> set[str]:
    return {
        word
        for word in normalized_text(value).split()
        if len(word) >= 4 and word not in STOP_WORDS
    }


def matching_spine_event(line: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    line_words = content_words(line)
    best: tuple[int, dict[str, Any]] = (0, {})
    for event in events:
        text = " ".join(str(event.get(key) or "") for key in [
            "title",
            "summary",
            "outcome",
            "evidence",
            "party_interpretation",
            "location",
        ])
        words = content_words(text)
        score = len(line_words & words)
        if score > best[0]:
            best = (score, event)
    return best[1] if best[0] >= 2 else {}


def normalize_event_type(event_type: str) -> str:
    value = normalized_text(event_type).replace(" ", "_")
    value = EVENT_TYPE_ALIASES.get(value, value)
    return value if value in REVIEW_EVENT_TYPES else "discovery"


def infer_event_type(line: str, spine_event: dict[str, Any], source_section: str = "") -> str:
    if spine_event.get("event_type"):
        return normalize_event_type(str(spine_event["event_type"]))
    if source_section in SECTION_EVENT_TYPE_HINTS:
        return SECTION_EVENT_TYPE_HINTS[source_section]
    normalized = normalized_text(line)
    if any(word in normalized for word in ["attack", "combat", "fight", "zombie"]):
        return "combat"
    if any(word in normalized for word in ["letter", "learn", "reveals", "lore"]):
        return "lore"
    if any(word in normalized for word in ["travel", "entered", "approached", "arrived"]):
        return "travel"
    if any(word in normalized for word in ["found", "discovered", "retrieved"]):
        return "discovery"
    return "social"


def importance_for(event_type: str, line: str) -> str:
    normalized = normalized_text(line)
    if event_type in {"combat", "cliffhanger", "lore_reveal"} or any(word in normalized for word in ["attack", "letter", "ismark", "bluetooth"]):
        return "high"
    return "medium"


def event_has_verb(text: str) -> bool:
    words = set(normalized_text(text).split())
    return bool(words & EVENT_VERBS)


def split_compound_event_line(line: str) -> list[str]:
    text = line.strip()
    if not text:
        return []
    separators = [r"\s+and then\s+", r"\s+then\s+", r";\s+", r"\.\s+"]
    parts = [text]
    for separator in separators:
        next_parts = []
        for part in parts:
            next_parts.extend(re.split(separator, part, flags=re.IGNORECASE))
        parts = next_parts
    cleaned = [part.strip(" .") for part in parts if part.strip(" .")]
    if len(cleaned) <= 1:
        return [text]
    if all(event_has_verb(part) and len(part) >= 20 for part in cleaned):
        return cleaned
    return [text]


def source_candidates_from_narrative(narrative: str) -> list[dict[str, str]]:
    sections = split_markdown_sections(narrative)
    candidates: list[dict[str, str]] = []
    for line in narrative_chronology_lines(narrative):
        for split_line in split_compound_event_line(line):
            candidates.append({"summary": split_line, "source_section": "## Chronological Major Events"})
    for section, event_type in SECTION_EVENT_TYPE_HINTS.items():
        for line in narrative_bullet_lines(sections.get(section, "")):
            for split_line in split_compound_event_line(line):
                candidates.append({
                    "summary": split_line,
                    "source_section": section,
                    "event_type_hint": event_type,
                })
    return candidates


def significant_overlap(left: str, right: str) -> bool:
    left_words = content_words(left)
    right_words = content_words(right)
    if not left_words or not right_words:
        return False
    smaller = min(len(left_words), len(right_words))
    shared = len(left_words & right_words)
    return shared >= max(3, int(smaller * 0.72))


def dedupe_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    kept: list[dict[str, str]] = []
    for candidate in candidates:
        summary = candidate.get("summary", "").strip()
        if len(summary) < 15:
            continue
        duplicate_index = None
        for index, existing in enumerate(kept):
            existing_summary = existing.get("summary", "")
            if normalized_text(summary) == normalized_text(existing_summary) or significant_overlap(summary, existing_summary):
                duplicate_index = index
                break
        if duplicate_index is None:
            kept.append(candidate)
            continue
        existing = kept[duplicate_index]
        if len(summary) > len(existing.get("summary", "")):
            merged = {**existing, **candidate}
            if existing.get("source_section") and candidate.get("source_section") != existing.get("source_section"):
                merged["source_section"] = f"{existing['source_section']}; {candidate['source_section']}"
            kept[duplicate_index] = merged
    return kept


def spine_bucket(spine_event: dict[str, Any]) -> str:
    order = spine_event.get("order")
    title = spine_event.get("title") or ""
    if order not in {None, ""} and title:
        return f"{order}. {title}"
    return str(title or order or "").strip()


def joined(values: Any) -> str:
    if isinstance(values, list):
        return ", ".join(str(value) for value in values if str(value).strip())
    return str(values or "").strip()


def verify_notes(spine_event: dict[str, Any], source_section: str) -> str:
    notes = []
    needs_review = spine_event.get("needs_review")
    if needs_review:
        notes.append(f"spine needs_review: {joined(needs_review)}")
    if "## Open Threads" in source_section:
        notes.append("open thread from narrative; confirm resolution status during review")
    return "; ".join(notes)


def render_event_record(index: int, line: str, spine_event: dict[str, Any], source_section: str = "", event_type_hint: str = "") -> str:
    event_type = normalize_event_type(event_type_hint) if event_type_hint else infer_event_type(line, spine_event, source_section)
    actors = ", ".join(spine_event.get("party_members") or []) or "Party"
    targets = joined(spine_event.get("entities") or spine_event.get("npcs") or [])
    items = joined(spine_event.get("items") or [])
    rich_type = str(spine_event.get("event_type") or event_type_hint or "").strip()
    tags = ", ".join(filter(None, [items, targets, f"source={source_section.replace('## ', '')}" if source_section else "", f"spine_type={rich_type}" if rich_type and normalize_event_type(rich_type) != rich_type else ""]))
    story_tags = ", ".join(filter(None, [spine_bucket(spine_event), str(spine_event.get("party_interpretation") or "").strip()]))
    return "\n".join([
        "EVENT:",
        f"timestamp: N/A",
        f"event_type: {event_type}",
        f"summary: {line}",
        f"actors: {actors}",
        f"targets: {targets}",
        f"location: {spine_event.get('location') or ''}",
        f"mechanical_tags: {tags}",
        f"story_tags: {story_tags}",
        f"outcome: {spine_event.get('outcome') or ''}",
        f"importance: {importance_for(event_type, line)}",
        "confidence: high",
        f"verify: {verify_notes(spine_event, source_section)}",
    ])


def deterministic_clean_events(session_name: str) -> str:
    narrative = read_text(narrative_path(session_name))
    candidates = source_candidates_from_narrative(narrative)
    spine = load_spine(session_name)
    spine_events = [event for event in spine.get("major_events") or [] if isinstance(event, dict)]
    if not candidates:
        candidates = [{"summary": str(event.get("summary") or event.get("title") or "").strip(), "source_section": "session spine"} for event in spine_events]
    else:
        represented = [matching_spine_event(candidate["summary"], spine_events) for candidate in candidates]
        represented_orders = {event.get("order") for event in represented if event}
        for event in spine_events:
            if event.get("order") not in represented_orders:
                line = str(event.get("summary") or event.get("title") or "").strip()
                if line:
                    candidates.append({
                        "summary": line,
                        "source_section": "session spine",
                        "event_type_hint": normalize_event_type(str(event.get("event_type") or "")),
                    })
    candidates = dedupe_candidates(candidates)
    records = []
    for index, candidate in enumerate(candidates, start=1):
        line = candidate["summary"]
        records.append(render_event_record(
            index,
            line,
            matching_spine_event(line, spine_events),
            candidate.get("source_section", ""),
            candidate.get("event_type_hint", ""),
        ))
    return "\n\n".join(records).strip() + "\n"


def event_source_packet(session_name: str) -> tuple[str, str]:
    narrative = narrative_path(session_name)
    if narrative.exists():
        sections = [
            optional_section("SESSION SPINE", spine_path(session_name)),
            optional_section("STEP 6 CLEAN NARRATIVE", narrative),
        ]
        return "\n\n".join(section for section in sections if section), "clean narrative and spine packet"

    source = curated_path(session_name)
    source_kind = "curated session packet"
    if not source.exists():
        source = transcript_path(session_name)
        source_kind = "transcript"
    return read_text(source), source_kind


def extract_session(session_name: str):
    output = events_path(session_name)

    if narrative_path(session_name).exists() and spine_path(session_name).exists():
        write_text(output, deterministic_clean_events(session_name))
        print(f"\nEvent extraction written to: {output}")
        return

    source_text, source_kind = event_source_packet(session_name)
    chunks = chunk_text(source_text)

    extract_prompt = load_prompt("extract_events")
    dnd_rules = load_prompt("dnd_event_rules")

    system_prompt = build_prompt(
        "You are a strict Dungeons & Dragons session event extractor.",
        dnd_rules,
        extract_prompt,
        "Do not summarize. Do not explain. Output ONLY event records."
    )

    results = []

    for index, chunk in enumerate(chunks, start=1):
        print(f"Extracting chunk {index} of {len(chunks)}...")

        user_prompt = f"""
Extract event records from this {source_kind} chunk.

Chunk: {index} of {len(chunks)}

SOURCE CHUNK:
{chunk}
"""

        result = chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=900,
        )

        results.append(f"\n\n# Extract Chunk {index}\n\n{result.strip()}")

    write_text(output, "\n".join(results))
    print(f"\nEvent extraction written to: {output}")
