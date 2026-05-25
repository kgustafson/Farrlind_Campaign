from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from raglib.campaign import load_campaign_metadata
from raglib.config import BASE2, CLEAN
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import generate
from raglib.prompts import load_prompt


DEFAULT_MODEL = "gemma4:e2b"
OLLAMA_OPTIONS = {
    "temperature": 0.1,
    "top_p": 0.9,
    "num_ctx": 32768,
}
REQUIRED_EVENT_KEYS = {
    "order",
    "title",
    "event_type",
    "location",
    "summary",
    "party_members",
    "npcs",
    "entities",
    "items",
    "party_interpretation",
    "outcome",
    "evidence",
    "needs_review",
}
NPC_ACTIVITY_MARKERS = {
    "appears",
    "attacks",
    "confronts",
    "draws",
    "explains",
    "fights",
    "guides",
    "leads",
    "meets",
    "reveals",
    "says",
    "speaks",
    "tells",
    "writes",
    "wrote",
}


def narrative_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_narrative.md"


def spine_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_spine.yaml"


def spine_metadata_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_spine_metadata.yaml"


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(BASE2))
    except ValueError:
        return str(path)


def build_spine_prompt(session_name: str, narrative: str) -> str:
    template = load_prompt("extract_session_spine")
    return (
        template
        .replace("sessionXX", session_name)
        .replace("clean/sessionXX_narrative.md", relative(narrative_path(session_name)))
        .replace("{preservation_checklist}", preservation_checklist(narrative))
        .rstrip()
        + "\n\n--- SESSION NARRATIVE START ---\n\n"
        + narrative.strip()
        + "\n\n--- SESSION NARRATIVE END ---\n"
    )


def extract_yaml_document(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    match = re.search(r"```(?:yaml|yml)?\s*(.*?)```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    try:
        document = yaml.safe_load(cleaned)
    except yaml.YAMLError:
        document = yaml.safe_load(quote_plain_scalars_with_colons(cleaned))
    if not isinstance(document, dict):
        raise ValueError("Session spine output must be a YAML mapping.")
    return document


def quote_plain_scalars_with_colons(text: str) -> str:
    repaired = []
    scalar_line = re.compile(r"^(\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_]*:\s+)(.+)$")
    for line in text.splitlines():
        match = scalar_line.match(line)
        if not match:
            repaired.append(line)
            continue
        prefix, value = match.groups()
        stripped = value.strip()
        if ": " not in stripped or stripped.startswith(("'", '"', "|", ">", "[", "{")):
            repaired.append(line)
            continue
        quoted = yaml.safe_dump(stripped, default_style='"', width=1000).strip()
        repaired.append(f"{prefix}{quoted}")
    return "\n".join(repaired)


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def campaign_npc_terms() -> set[str]:
    terms: set[str] = set()
    for item in load_campaign_metadata().get("glossary") or []:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        note = normalized_text(item.get("note"))
        if term and any(marker in note for marker in ["npc", "burgomaster", "vampire lord", "daughter", "son"]):
            terms.add(term)
        for alias in item.get("aliases") or []:
            alias = str(alias or "").strip()
            if alias and term:
                terms.add(alias)
    return terms


def possessive_or_named_location_context_only(event: dict[str, Any], npc: str) -> bool:
    normalized_npc = normalized_text(npc)
    if not normalized_npc:
        return False
    location = normalized_text(event.get("location"))
    text = normalized_text(" ".join([
        str(event.get("title") or ""),
        str(event.get("summary") or ""),
        str(event.get("outcome") or ""),
        str(event.get("evidence") or ""),
    ]))
    active = any(marker in text for marker in NPC_ACTIVITY_MARKERS)
    if active:
        return False
    if normalized_npc in location:
        return True
    possessive = f"{normalized_npc} s"
    return possessive in text and any(place in text for place in ["mansion", "house", "castle", "letter", "note"])


def postprocess_spine(document: dict[str, Any]) -> dict[str, Any]:
    npc_terms = campaign_npc_terms()
    canonical_by_alias = {normalized_text(term): term for term in npc_terms}
    for event in document.get("major_events") or []:
        kept_npcs = []
        review_notes = normalize_string_list(event.get("needs_review"))
        for npc in normalize_string_list(event.get("npcs")):
            canonical = canonical_by_alias.get(normalized_text(npc), npc)
            if possessive_or_named_location_context_only(event, canonical):
                review_notes.append(f"{canonical} appears contextual to a named place/item, not necessarily present in this event.")
                continue
            kept_npcs.append(npc)
        event["npcs"] = kept_npcs
        event["needs_review"] = review_notes
    return document


SECTION_RE = re.compile(r"^## .+$", re.MULTILINE)


def split_markdown_sections(text: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(0).strip()] = text[match.end():end].strip()
    return sections


def preservation_checklist(narrative: str) -> str:
    sections = split_markdown_sections(narrative)
    lines: list[str] = []
    for heading in [
        "## Combat And Encounters",
        "## Items Loot And Resources",
        "## Character Notes",
        "## Open Threads",
    ]:
        body = sections.get(heading, "")
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if line.startswith(("-", "*")) and "None identified" not in line:
                lines.append(line)
    if not lines:
        return "- None identified."
    return "\n".join(lines[:32])


def narrative_item_names(narrative: str) -> list[str]:
    items: list[str] = []
    body = split_markdown_sections(narrative).get("## Items Loot And Resources", "")
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith(("-", "*")):
            continue
        match = re.search(r"\*\*(.+?)\*\*", line)
        if match:
            title = match.group(1).strip(" :-")
        else:
            title = re.sub(r"^[-*]\s*", "", line).split(" - ", 1)[0].split(":", 1)[0].strip()
        for part in re.split(r"\s+and\s+|/", title):
            cleaned = part.strip(" :-")
            if cleaned and normalized_text(cleaned) not in {"items loot resources", "none identified"}:
                items.append(cleaned)
    return list(dict.fromkeys(items))


def narrative_cliffhanger_lines(narrative: str) -> list[str]:
    lines: list[str] = []
    for heading in ["## Combat And Encounters", "## Open Threads", "## Needs Review"]:
        body = split_markdown_sections(narrative).get(heading, "")
        for raw_line in body.splitlines():
            line = raw_line.strip()
            norm = normalized_text(line)
            if line.startswith(("-", "*")) and any(marker in norm for marker in ["cliffhanger", "mid attack", "session ended", "bluetooth", "ismark"]):
                lines.append(re.sub(r"^[-*]\s*", "", line).strip())
    return list(dict.fromkeys(lines))


def narrative_character_lines(narrative: str) -> list[str]:
    lines: list[str] = []
    body = split_markdown_sections(narrative).get("## Character Notes", "")
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith(("-", "*")) and "None identified" not in line:
            lines.append(re.sub(r"^[-*]\s*", "", line).strip())
    return list(dict.fromkeys(lines))


def event_combined_text(events: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for event in events:
        for key in ["title", "summary", "outcome", "evidence", "party_interpretation"]:
            parts.append(str(event.get(key) or ""))
        for key in ["items", "entities", "npcs", "party_members", "needs_review"]:
            parts.extend(normalize_string_list(event.get(key)))
    return " ".join(parts)


def event_mentions(events: list[dict[str, Any]], term: str) -> bool:
    return normalized_text(term) in normalized_text(event_combined_text(events))


def apply_narrative_preservation(document: dict[str, Any], narrative: str) -> dict[str, Any]:
    events = document.get("major_events") or []
    if not events or not narrative:
        return document

    missing_items = [item for item in narrative_item_names(narrative) if not event_mentions(events, item)]
    if missing_items:
        target = first_event_of_type(events, {"discovery", "resource_change", "combat"}) or events[0]
        existing_items = normalize_string_list(target.get("items"))
        target["items"] = list(dict.fromkeys([*existing_items, *missing_items]))
        notes = normalize_string_list(target.get("needs_review"))
        notes.append(f"Preserved narrative item/resource beat(s): {', '.join(missing_items)}.")
        target["needs_review"] = list(dict.fromkeys(notes))

    for character_line in narrative_character_lines(narrative):
        if event_mentions(events, character_line):
            continue
        target = first_event_of_type(events, {"combat", "resource_change"}) or events[0]
        match = re.search(r"\*\*(.+?)\*\*", character_line)
        if match:
            party_members = normalize_string_list(target.get("party_members"))
            party_members.append(match.group(1).strip())
            target["party_members"] = list(dict.fromkeys(party_members))
        notes = normalize_string_list(target.get("needs_review"))
        notes.append(f"Preserved narrative character/resource beat: {character_line}")
        target["needs_review"] = list(dict.fromkeys(notes))

    cliffhangers = narrative_cliffhanger_lines(narrative)
    if cliffhangers and not any(event.get("event_type") == "cliffhanger" for event in events):
        if not any(event_mentions([event], "Bluetooth") or event_mentions([event], "Ismark") for event in events):
            events.append({
                "order": len(events) + 1,
                "title": "Final Confrontation Cliffhanger",
                "event_type": "cliffhanger",
                "location": latest_event_location(events) or "",
                "summary": cliffhangers[0],
                "party_members": [],
                "npcs": [],
                "entities": [],
                "items": [],
                "party_interpretation": "",
                "outcome": "Session ends before the confrontation is resolved.",
                "evidence": cliffhangers[0],
                "needs_review": ["Added from narrative cliffhanger/open-thread preservation."],
            })
        else:
            target = events[-1]
            notes = normalize_string_list(target.get("needs_review"))
            notes.append(f"Preserved narrative cliffhanger beat: {cliffhangers[0]}")
            target["needs_review"] = list(dict.fromkeys(notes))

    return document


def first_event_of_type(events: list[dict[str, Any]], event_types: set[str]) -> dict[str, Any] | None:
    for event in events:
        if str(event.get("event_type") or "") in event_types:
            return event
    return None


def latest_event_location(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        location = str(event.get("location") or "").strip()
        if location:
            return location
    return ""


def normalize_major_event(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"title": str(item), "summary": str(item)}
    normalized = {key: item.get(key) for key in REQUIRED_EVENT_KEYS}
    normalized["order"] = int(item.get("order") or index)
    for key in ["title", "event_type", "location", "summary", "party_interpretation", "outcome", "evidence"]:
        normalized[key] = str(normalized.get(key) or "").strip()
    for key in ["party_members", "npcs", "entities", "items", "needs_review"]:
        normalized[key] = normalize_string_list(normalized.get(key))
    if not normalized["event_type"]:
        normalized["event_type"] = "other"
    return normalized


def normalize_spine(document: dict[str, Any], session_name: str, narrative: str = "") -> dict[str, Any]:
    timeline = document.get("timeline") if isinstance(document.get("timeline"), dict) else {}
    major_events = [
        normalize_major_event(item, index)
        for index, item in enumerate(document.get("major_events") or [], start=1)
    ]
    major_events.sort(key=lambda item: item["order"])
    for index, item in enumerate(major_events, start=1):
        item["order"] = index
    normalized = {
        "session": str(document.get("session") or session_name),
        "source": relative(narrative_path(session_name)),
        "timeline": {
            "starting_location": str(timeline.get("starting_location") or "").strip(),
            "ending_location": str(timeline.get("ending_location") or "").strip(),
            "real_world_date": str(timeline.get("real_world_date") or "N/A").strip() or "N/A",
            "in_world_date": str(timeline.get("in_world_date") or "N/A").strip() or "N/A",
        },
        "major_events": major_events,
        "open_threads": normalize_string_list(document.get("open_threads")),
        "needs_review": normalize_string_list(document.get("needs_review")),
    }
    normalized = postprocess_spine(normalized)
    normalized = apply_narrative_preservation(normalized, narrative)
    validate_spine(normalized)
    return normalized


def validate_spine(document: dict[str, Any]) -> None:
    events = document.get("major_events") or []
    if not events:
        raise ValueError("Session spine must include at least one major event.")
    for event in events:
        missing = [key for key in ["order", "title", "summary"] if not event.get(key)]
        if missing:
            raise ValueError(f"Major event {event.get('order') or '?'} missing required fields: {', '.join(missing)}")


def extract_session_spine(session_name: str, model: Optional[str] = None) -> None:
    model = model or os.environ.get("FARRLIND_SPINE_MODEL", DEFAULT_MODEL)
    narrative = read_text(narrative_path(session_name))
    prompt = build_spine_prompt(session_name, narrative)
    print(f"Extracting session spine with {model}...")
    started = time.monotonic()
    raw_output = generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)
    duration = time.monotonic() - started
    spine = normalize_spine(extract_yaml_document(raw_output), session_name, narrative)
    metadata = {
        "session": session_name,
        "model": model,
        "source": relative(narrative_path(session_name)),
        "output": relative(spine_path(session_name)),
        "major_event_count": len(spine["major_events"]),
        "duration_seconds": round(duration, 2),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_text(spine_path(session_name), yaml.safe_dump(spine, sort_keys=False, allow_unicode=True))
    write_text(spine_metadata_path(session_name), yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True))
    print(f"Session spine written to: {spine_path(session_name)}")
