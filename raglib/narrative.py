from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from raglib.campaign import campaign_metadata_path, load_campaign_metadata
from raglib.config import BASE2, CLEAN, RAW, SESSIONS
from raglib.curate import campaign_glossary, canon_scrub, split_transcript
from raglib.extraction_hygiene import PARTY_FRAMING_MARKERS, PARTY_INTERPRETATION_MARKERS, WORLD_FACT_MARKERS, has_any_marker, normalized_text
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import generate
from raglib.prompts import load_prompt


DEFAULT_MODEL = "gemma4:e2b"
CHUNK_SIZE = 22000
CHUNK_OVERLAP = 1500
OLLAMA_OPTIONS = {
    "temperature": 0.15,
    "top_p": 0.9,
    "num_ctx": 32768,
}
SECTION_RE = re.compile(r"^## .+$", re.MULTILINE)
NPC_SECTION = "## Key NPCs And Entities"
INTERPRETATION_SECTION = "## Party Interpretations Versus World Facts"
OBJECTIVE_SECTIONS_FOR_INTERPRETATION_REVIEW = {
    "## Chronological Major Events",
    "## Key Locations",
    NPC_SECTION,
    "## Combat And Encounters",
    "## Items Loot And Resources",
    "## Open Threads",
    "## Timeline Seeds",
}
NARRATIVE_INTERPRETATION_MARKERS = PARTY_INTERPRETATION_MARKERS | PARTY_FRAMING_MARKERS | {
    "burger master",
    "customer service",
    "meal plan",
    "proprietary",
    "recipe",
    "resort management",
    "resort manager",
    "yelp",
}


def transcript_path(session_name: str) -> Path:
    return RAW / f"{session_name}_transcript.txt"


def curated_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_curated.md"


def diary_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_diary.md"


def session_context_path(session_name: str) -> Path:
    return SESSIONS / f"{session_name}_context.yaml"


def narrative_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_narrative.md"


def narrative_metadata_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_narrative_metadata.json"


def narrative_chunks_dir(session_name: str) -> Path:
    return CLEAN / f"{session_name}_narrative_chunks"


def limited_session_context(session_name: str) -> str:
    parts = [f"Session: {session_name}"]
    context_path = session_context_path(session_name)
    if context_path.exists():
        parts.extend(["", "Session context file:", read_text(context_path)])
    return "\n".join(parts)


def render_prompt(template_name: str, session_name: str) -> str:
    template = load_prompt(template_name)
    return (
        template
        .replace("{campaign_glossary}", campaign_glossary())
        .replace("{session_context}", limited_session_context(session_name))
    )


def build_chunk_prompt(prompt_text: str, session_name: str, chunk_text: str, chunk_index: int, chunk_count: int) -> str:
    return (
        f"{prompt_text.rstrip()}\n\n"
        f"Session: {session_name}\n"
        f"Chunk: {chunk_index} of {chunk_count}\n\n"
        "--- TRANSCRIPT CHUNK START ---\n\n"
        f"{chunk_text}\n\n"
        "--- TRANSCRIPT CHUNK END ---\n"
    )


def optional_source_section(label: str, path: Path, max_chars: int) -> tuple[str, str | None]:
    if not path.exists():
        return "", None
    text = read_text(path).strip()
    if not text:
        return "", None
    truncated = canon_scrub(text)[:max_chars]
    section = f"--- {label} START ---\n\n{truncated}\n\n--- {label} END ---"
    return section, relative(path)


def supported_source_section(label: str, path: Path, support_text: str, max_chars: int) -> tuple[str, str | None]:
    if not path.exists():
        return "", None
    text = read_text(path).strip()
    if not text:
        return "", None
    supported = filter_lines_to_supported_source(canon_scrub(text), support_text)
    truncated = supported[:max_chars]
    section = (
        f"--- {label} START ---\n\n"
        "These are step 5 curated excerpts whose details appear supported by active-session chunk notes/transcript. "
        "Do not use omitted curated details as current-session facts.\n\n"
        f"{truncated}\n\n--- {label} END ---"
    )
    return section, relative(path)


def filter_lines_to_supported_source(text: str, support_text: str) -> str:
    if not support_text.strip():
        return text
    kept: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            kept.append(line)
            continue
        if line_supported_by_text(stripped, support_text):
            kept.append(line)
    return "\n".join(kept).strip()


def line_supported_by_text(line: str, support_text: str) -> bool:
    phrases = high_signal_phrases(line)
    if not phrases:
        return True
    hits = sum(1 for phrase in phrases if text_contains_phrase(support_text, phrase))
    return hits > 0


def build_synthesis_prompt(
    prompt_text: str,
    session_name: str,
    chunk_outputs: list[str],
    curated_section: str,
    diary_section: str,
    recap_context_section: str = "",
) -> str:
    extracts = []
    for index, output in enumerate(chunk_outputs, start=1):
        extracts.append(f"--- NARRATIVE CHUNK NOTES {index} START ---\n\n{output.strip()}\n\n--- NARRATIVE CHUNK NOTES {index} END ---")
    sections = [
        prompt_text.rstrip(),
        f"Session: {session_name}",
        recap_context_section,
        curated_section,
        diary_section,
        "\n\n".join(extracts),
    ]
    return "\n\n".join(section for section in sections if section.strip()) + "\n"


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(BASE2))
    except ValueError:
        return str(path)


def existing_step_six_sources(session_name: str) -> list[str]:
    sources = []
    for path in [
        campaign_metadata_path(),
        transcript_path(session_name),
        curated_path(session_name),
        diary_path(session_name),
        session_context_path(session_name),
    ]:
        if path.exists():
            sources.append(relative(path))
    return sources


def campaign_party_terms() -> set[str]:
    metadata = load_campaign_metadata()
    terms: set[str] = set()
    for member in metadata.get("party") or []:
        for key in ["character_name", "full_name", "player_name"]:
            value = str(member.get(key) or "").strip()
            if value:
                terms.add(value)
        for alias in member.get("aliases") or []:
            alias = str(alias or "").strip()
            if alias:
                terms.add(alias)
    return terms


def campaign_controlled_companion_terms() -> set[str]:
    metadata = load_campaign_metadata()
    terms: set[str] = set()
    for item in metadata.get("glossary") or []:
        if not isinstance(item, dict):
            continue
        note = normalized_text(item.get("note"))
        if not any(marker in note for marker in ["familiar", "companion", "steel defender", "party resource"]):
            continue
        term = str(item.get("term") or "").strip()
        if term:
            terms.add(term)
        for alias in item.get("aliases") or []:
            alias = str(alias or "").strip()
            if alias:
                terms.add(alias)
    return terms


def is_party_or_companion_heading(line: str, blocked_terms: set[str]) -> bool:
    match = re.match(r"^\s*[-*]\s+\*\*(.+?)\*\*", line)
    if not match:
        return False
    heading = normalized_text(match.group(1))
    return any(heading == normalized_text(term) for term in blocked_terms if normalized_text(term))


def split_markdown_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return text, []
    intro = text[:matches[0].start()].rstrip()
    sections = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(0).strip()
        body = text[match.end():end].strip()
        sections.append((heading, body))
    return intro, sections


def render_markdown_sections(intro: str, sections: list[tuple[str, str]]) -> str:
    parts = [intro.strip()] if intro.strip() else []
    for heading, body in sections:
        parts.append(f"{heading}\n\n{body.strip() if body.strip() else '- None identified.'}")
    return "\n\n".join(parts).strip() + "\n"


def looks_like_interpretation_line(line: str) -> bool:
    if has_any_marker(line, WORLD_FACT_MARKERS):
        return False
    normalized = normalized_text(line)
    party_framing = any(marker in normalized for marker in ["party", "they", "triplets", "character"])
    return party_framing and has_any_marker(line, NARRATIVE_INTERPRETATION_MARKERS)


def split_objective_and_interpretive_clauses(line: str) -> tuple[str, list[str]]:
    bullet_match = re.match(r"^(\s*[-*]\s+\*\*.+?\*\*\s+-\s+)(.+)$", line)
    if not bullet_match:
        return ("", [line]) if looks_like_interpretation_line(line) else (line, [])

    prefix, description = bullet_match.groups()
    clauses = [clause.strip() for clause in re.split(r";\s*", description) if clause.strip()]
    if len(clauses) < 2:
        return ("", [line]) if looks_like_interpretation_line(line) else (line, [])

    kept = []
    moved = []
    for clause in clauses:
        if has_any_marker(clause, NARRATIVE_INTERPRETATION_MARKERS) and not has_any_marker(clause, WORLD_FACT_MARKERS):
            moved.append(f"{prefix}{clause}")
        else:
            kept.append(clause)
    kept_line = f"{prefix}{'; '.join(kept)}" if kept else ""
    return kept_line, moved


def add_interpretation_bullets(body: str, bullets: list[str]) -> str:
    existing = body.strip()
    if existing == "- None identified.":
        existing = ""
    additions = []
    for bullet in bullets:
        cleaned = re.sub(r"^\s*[-*]\s*", "", bullet).strip()
        if not cleaned:
            continue
        additions.append(f"- **Party interpretation** - {cleaned}")
    combined = "\n".join(part for part in [existing, *additions] if part.strip()).strip()
    return combined or "- None identified."


def latest_supported_ending_location(chunk_outputs: list[str]) -> str:
    for output in reversed(chunk_outputs):
        candidates = [line.strip() for line in output.splitlines() if line.strip().startswith(("*", "-"))]
        for line in reversed(candidates):
            normalized = normalized_text(line)
            if "mansion" in normalized and any(marker in normalized for marker in ["door", "confront", "ismark", "bluetooth", "leads", "led"]):
                return "Strahd von Zarovich's Mansion."
            if "burgomaster" in normalized and any(marker in normalized for marker in ["house", "door", "marina", "ismark"]):
                return "Burgomaster's House."
        for line in reversed(candidates):
            normalized = normalized_text(line)
            if "blood on the vine" in normalized:
                return "Blood on the Vine."
            if "village of barovia" in normalized:
                return "Village of Barovia."
    return ""


def replace_timeline_ending_location(body: str, ending_location: str) -> str:
    if not ending_location:
        return body
    lines = body.splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if re.match(r"^\s*[-*]\s*Ending location\s*:", line, flags=re.IGNORECASE):
            lines[index] = f"- Ending location: {ending_location}"
            replaced = True
            break
    if not replaced:
        lines.append(f"- Ending location: {ending_location}")
    return "\n".join(lines).strip()


def postprocess_narrative(
    text: str,
    chunk_outputs: Optional[list[str]] = None,
    active_transcript: str = "",
    recap_text: str = "",
) -> str:
    text = canon_scrub(text)
    intro, sections = split_markdown_sections(text)
    if not sections:
        return text

    blocked_terms = campaign_party_terms() | campaign_controlled_companion_terms()
    support_text = "\n\n".join([active_transcript, *(chunk_outputs or [])])
    known_roles = campaign_glossary_roles()
    companion_owners = campaign_companion_owners()
    relocated_interpretations: list[str] = []
    needs_review_notes: list[str] = []
    ending_location = latest_supported_ending_location(chunk_outputs or [])
    intro_paragraphs = []
    for paragraph in re.split(r"\n\s*\n", intro.strip()):
        paragraph = remove_recap_only_sentences(paragraph, active_transcript, recap_text)
        paragraph = remove_unsupported_sentences(paragraph, support_text)
        if not paragraph.strip():
            continue
        if looks_like_interpretation_line(paragraph):
            relocated_interpretations.append(paragraph)
            continue
        intro_paragraphs.append(paragraph)
    intro = "\n\n".join(intro_paragraphs)
    processed: list[tuple[str, str]] = []

    for heading, body in sections:
        kept_lines = []
        for line in body.splitlines():
            line = remove_recap_only_sentences(line, active_transcript, recap_text)
            line = remove_unsupported_sentences(line, support_text)
            if not line.strip():
                continue
            if heading == NPC_SECTION and is_party_or_companion_heading(line, blocked_terms):
                continue
            if heading == NPC_SECTION:
                line, role_note = apply_known_role_hygiene(line, known_roles)
                if role_note:
                    needs_review_notes.append(role_note)
            line, location_note = apply_found_location_hygiene(line, active_transcript)
            if location_note:
                needs_review_notes.append(location_note)
            if heading == "## Character Notes":
                line, ownership_note = apply_companion_ownership_hygiene(line, companion_owners)
                if ownership_note:
                    needs_review_notes.append(ownership_note)
            if heading in OBJECTIVE_SECTIONS_FOR_INTERPRETATION_REVIEW and looks_like_interpretation_line(line):
                kept_line, moved_lines = split_objective_and_interpretive_clauses(line)
                relocated_interpretations.extend(moved_lines)
                if not kept_line:
                    continue
                line = kept_line
            kept_lines.append(line)
        new_body = "\n".join(kept_lines).strip()
        if heading == "## Timeline Seeds":
            new_body = replace_timeline_ending_location(new_body, ending_location)
        if heading == NPC_SECTION and not any(line.strip().startswith(("-", "*")) for line in kept_lines):
            new_body = "- None identified."
        processed.append((heading, new_body))

    if needs_review_notes:
        processed = append_needs_review(processed, needs_review_notes)

    if relocated_interpretations:
        for index, (heading, body) in enumerate(processed):
            if heading == INTERPRETATION_SECTION:
                processed[index] = (heading, add_interpretation_bullets(body, relocated_interpretations))
                break
        else:
            processed.append((INTERPRETATION_SECTION, add_interpretation_bullets("", relocated_interpretations)))

    return render_markdown_sections(intro, processed)


def campaign_glossary_roles() -> dict[str, str]:
    metadata = load_campaign_metadata()
    roles: dict[str, str] = {}
    for item in metadata.get("glossary") or []:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        note = str(item.get("note") or "").strip()
        if term and note:
            roles[normalized_text(term)] = note
            for alias in item.get("aliases") or []:
                alias = str(alias or "").strip()
                if alias:
                    roles[normalized_text(alias)] = note
    return roles


def campaign_companion_owners() -> dict[str, str]:
    metadata = load_campaign_metadata()
    owners: dict[str, str] = {}
    party_names = {
        normalized_text(str(member.get("character_name") or "")): str(member.get("character_name") or "").strip()
        for member in metadata.get("party") or []
        if isinstance(member, dict)
    }
    for item in metadata.get("glossary") or []:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        note = str(item.get("note") or "").strip()
        owner_match = re.search(r"\b([A-Z][A-Za-z']+)'s\b", note)
        if not term or not owner_match:
            continue
        owner = party_names.get(normalized_text(owner_match.group(1)), owner_match.group(1))
        owner_terms = [term, *(str(alias or "").strip() for alias in item.get("aliases") or [])]
        for owner_term in owner_terms:
            if owner_term:
                owners[normalized_text(owner_term)] = owner
    return owners


def apply_known_role_hygiene(line: str, known_roles: dict[str, str]) -> tuple[str, str | None]:
    match = re.match(r"^(\s*[-*]\s+\*\*(.+?)\*\*\s+-\s+)(.+)$", line)
    if not match:
        return line, None
    prefix, heading, description = match.groups()
    lookup_heading = re.sub(r"\s*\(.+?\)\s*", "", heading).strip()
    role = known_roles.get(normalized_text(heading)) or known_roles.get(normalized_text(lookup_heading))
    if not role:
        return line, None
    desc_norm = normalized_text(description)
    role_norm = normalized_text(role)
    suspicious = [
        "one of the party",
        "party member",
        "vampire lord",
        "bartender",
        "dm",
        "player",
    ]
    if any(marker in desc_norm and marker not in role_norm for marker in suspicious):
        return f"{prefix}{role}", f"Known role corrected for {heading}: model output said `{description}`."
    return line, None


def apply_found_location_hygiene(line: str, active_transcript: str) -> tuple[str, str | None]:
    match = re.search(r"\b(F|f)ound\s+(?:among|in|inside|at|from)\s+the\s+([A-Za-z][A-Za-z' -]{2,80})", line)
    if not match:
        return line, None
    phrase = match.group(0)
    if text_contains_phrase(active_transcript, phrase):
        return line, None
    cleaned = line[:match.start()].rstrip(" ,;:-") + " found; exact source/location needs review" + line[match.end():]
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, f"Unsupported found-location claim changed to needs review: `{phrase}`."


def apply_companion_ownership_hygiene(line: str, companion_owners: dict[str, str]) -> tuple[str, str | None]:
    match = re.match(r"^(\s*[-*]\s+\*\*(.+?)\*\*\s+-\s+)(.+)$", line)
    if not match:
        return line, None
    prefix, heading, description = match.groups()
    heading_clean = re.sub(r"\s*\(.+?\)\s*", "", heading).strip()
    description_parts = [part.strip() for part in re.split(r";\s*", description) if part.strip()]
    kept: list[str] = []
    notes: list[str] = []
    for part in description_parts:
        part_norm = normalized_text(part)
        removed = False
        for companion_norm, owner in companion_owners.items():
            if companion_norm in part_norm and normalized_text(owner) != normalized_text(heading_clean):
                ownership_action = any(marker in part_norm for marker in ["manifest", "manifested", "summon", "summoned", "familiar"])
                if ownership_action:
                    notes.append(f"Companion ownership corrected for {heading}: `{part}` belongs with {owner}.")
                    removed = True
                    break
        if not removed:
            kept.append(part)
    if not kept:
        return "", "; ".join(notes) if notes else None
    return f"{prefix.replace(heading, heading_clean)}{'; '.join(kept)}", "; ".join(notes) if notes else None


def append_needs_review(sections: list[tuple[str, str]], notes: list[str]) -> list[tuple[str, str]]:
    deduped = list(dict.fromkeys(notes))
    additions = [f"- {note}" for note in deduped]
    for index, (heading, body) in enumerate(sections):
        if heading == "## Needs Review":
            existing = "" if body.strip() == "- None identified." else body.strip()
            joined = "\n".join(part for part in [existing, *additions] if part.strip())
            sections[index] = (heading, joined)
            break
    else:
        sections.append(("## Needs Review", "\n".join(additions)))
    return sections


def remove_recap_only_sentences(text: str, active_transcript: str, recap_text: str) -> str:
    if not active_transcript.strip() or not recap_text.strip() or not text.strip():
        return text
    bullet_prefix = ""
    bullet_match = re.match(r"^(\s*[-*]\s+)(.+)$", text)
    body = text
    if bullet_match:
        bullet_prefix, body = bullet_match.groups()

    parts = re.split(r"(?<=[.!?])\s+", body)
    kept = [part for part in parts if part.strip() and not is_recap_only_text(part, active_transcript, recap_text)]
    if not kept:
        return ""
    return bullet_prefix + " ".join(kept)


def remove_unsupported_sentences(text: str, support_text: str) -> str:
    if not support_text.strip() or not text.strip():
        return text
    bullet_prefix = ""
    bullet_match = re.match(r"^(\s*[-*]\s+)(.+)$", text)
    body = text
    if bullet_match:
        bullet_prefix, body = bullet_match.groups()
    parts = re.split(r"(?<=[.!?])\s+", body)
    kept = [part for part in parts if part.strip() and sentence_supported_by_text(part, support_text)]
    if not kept:
        return ""
    return bullet_prefix + " ".join(kept)


def sentence_supported_by_text(text: str, support_text: str) -> bool:
    phrases = high_signal_phrases(text)
    if not phrases:
        return True
    hits = sum(1 for phrase in phrases if text_contains_phrase(support_text, phrase))
    return hits > 0


def is_recap_only_text(text: str, active_transcript: str, recap_text: str) -> bool:
    normalized = normalized_text(text)
    if len(normalized.split()) < 4:
        return False
    phrases = recap_phrase_candidates(text)
    if not phrases:
        return False
    recap_only_hits = [
        phrase
        for phrase in phrases
        if text_contains_phrase(recap_text, phrase) and not text_contains_phrase(active_transcript, phrase)
    ]
    return bool(recap_only_hits)


def recap_phrase_candidates(text: str) -> list[str]:
    ignored = {
        "party found",
        "party discussed",
        "party traveled",
        "the party",
        "barovia party",
        "stradh von",
        "von zarovich",
    }
    words = [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z']+", text.lower())
        if len(word) >= 4 and word not in {"party", "they", "then", "with", "from", "into", "that", "this", "were", "which"}
    ]
    phrases = []
    for size in (3, 2):
        for index in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[index:index + size])
            if phrase not in ignored:
                phrases.append(phrase)
    return list(dict.fromkeys(phrases))


def high_signal_phrases(text: str) -> list[str]:
    ignored_words = {
        "about",
        "after",
        "also",
        "being",
        "during",
        "from",
        "into",
        "party",
        "that",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "with",
        "which",
    }
    words = [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z']+", text.lower())
        if len(word) >= 4 and word not in ignored_words
    ]
    phrases: list[str] = []
    for size in (3, 2):
        for index in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[index:index + size])
            if not any(generic in phrase for generic in ["session narrative", "major events", "none identified"]):
                phrases.append(phrase)
    return list(dict.fromkeys(phrases))


def text_contains_phrase(source: str, phrase: str) -> bool:
    normalized_source = f" {normalized_text(source)} "
    normalized_phrase = normalized_text(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in normalized_source


def strip_intro_ad_markers(text: str) -> str:
    lines = text.splitlines()
    first_session_line = None
    patterns = [
        re.compile(r"\bwhen last we left\b", re.IGNORECASE),
        re.compile(r"\bwe rejoin\b", re.IGNORECASE),
        re.compile(r"\bthe session (begins|starts|opens)\b", re.IGNORECASE),
        re.compile(r"\bwelcome back\b", re.IGNORECASE),
    ]
    for index, line in enumerate(lines[:220]):
        if any(pattern.search(line) for pattern in patterns):
            first_session_line = index
            break
    if first_session_line is None or first_session_line < 8:
        return text
    preamble = "\n".join(lines[:first_session_line])
    if re.search(r"\b(sponsor|patreon|merch|theme song|intro music|ad break)\b", preamble, re.IGNORECASE):
        return "\n".join(lines[first_session_line:])
    return text


def split_recap_and_active_session(text: str) -> tuple[str, str, str]:
    """Return active transcript, prior recap/context, and the marker used."""
    cleaned = strip_intro_ad_markers(text)
    markers = [
        "that is where we are now",
        "and that is where we are now",
        "so, you're making your way",
        "so you're making your way",
        "we rejoin",
        "when last we left",
    ]
    lowered = cleaned.lower()
    positions: list[tuple[int, str]] = []
    for marker in markers:
        position = lowered.find(marker)
        if position != -1:
            positions.append((position, marker))
    if not positions:
        return cleaned, "", ""
    position, marker = min(positions, key=lambda item: item[0])
    if marker in {"we rejoin", "when last we left"} and position < 2000:
        return cleaned, "", ""
    recap = cleaned[:position].strip()
    active = cleaned[position:].strip()
    return active or cleaned, recap, marker


def recap_context_section(recap_text: str, max_chars: int = 12000) -> str:
    recap_text = canon_scrub(recap_text.strip())
    if not recap_text:
        return ""
    if len(recap_text) > max_chars:
        recap_text = recap_text[-max_chars:]
    return (
        "--- PRIOR RECAP CONTEXT START ---\n\n"
        "This material is recap/context only. Use it to understand the starting situation, "
        "but do not turn it into current-session chronological events, encounters, loot, "
        "or character turns unless active session chunk notes also support them.\n\n"
        f"{recap_text}\n\n"
        "--- PRIOR RECAP CONTEXT END ---"
    )


def generate_narrative_summary(session_name: str, model: Optional[str] = None) -> None:
    model = model or os.environ.get("FARRLIND_NARRATIVE_MODEL", DEFAULT_MODEL)
    active_transcript, recap_text, active_marker = split_recap_and_active_session(read_text(transcript_path(session_name)))
    transcript = active_transcript
    chunks = split_transcript(transcript, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    chunks_dir = narrative_chunks_dir(session_name)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    chunk_prompt_text = render_prompt("narrative_chunk_notes", session_name)
    synthesis_prompt_text = render_prompt("generate_narrative_summary", session_name)

    chunk_outputs = []
    chunk_metadata = []
    total_duration = 0.0

    for index, chunk in enumerate(chunks, start=1):
        print(f"Generating narrative notes chunk {index} of {len(chunks)} with {model}...")
        started = time.monotonic()
        output = generate(
            build_chunk_prompt(chunk_prompt_text, session_name, chunk, index, len(chunks)),
            model=model,
            timeout=1800,
            options=OLLAMA_OPTIONS,
        ).strip()
        duration = time.monotonic() - started
        total_duration += duration
        output = canon_scrub(output)
        chunk_path = chunks_dir / f"chunk_{index:03d}.md"
        write_text(chunk_path, output + "\n")
        chunk_outputs.append(output)
        chunk_metadata.append({
            "chunk": index,
            "chars": len(chunk),
            "duration_seconds": round(duration, 2),
            "output": relative(chunk_path),
        })

    chunk_support_text = "\n\n".join([active_transcript, *chunk_outputs])
    curated_section, curated_source = supported_source_section(
        "STEP 5 CURATED PACKET ACTIVE-SUPPORTED EXCERPTS",
        curated_path(session_name),
        chunk_support_text,
        30000,
    )
    diary_section, diary_source = optional_source_section("OPTIONAL DIARY SOURCE", diary_path(session_name), 16000)
    recap_section = recap_context_section(recap_text)

    print(f"Synthesizing narrative draft with {model}...")
    started = time.monotonic()
    final_output = generate(
        build_synthesis_prompt(synthesis_prompt_text, session_name, chunk_outputs, curated_section, diary_section, recap_section),
        model=model,
        timeout=1800,
        options=OLLAMA_OPTIONS,
    ).strip()
    synthesis_duration = time.monotonic() - started
    total_duration += synthesis_duration
    final_output = postprocess_narrative(final_output, chunk_outputs, active_transcript=active_transcript, recap_text=recap_text)

    write_text(narrative_path(session_name), final_output + "\n")
    source_manifest = existing_step_six_sources(session_name)
    metadata = {
        "model": model,
        "session": session_name,
        "output": relative(narrative_path(session_name)),
        "allowed_source_boundary": "workflow_steps_1_through_5_only",
        "sources": source_manifest,
        "curated_source": curated_source,
        "diary_source": diary_source,
        "chunk_count": len(chunks),
        "chunk_size_chars": CHUNK_SIZE,
        "chunk_overlap_chars": CHUNK_OVERLAP,
        "active_session_boundary_marker": active_marker or None,
        "recap_context_chars": len(recap_text),
        "active_transcript_chars": len(active_transcript),
        "duration_seconds": round(total_duration, 2),
        "synthesis_duration_seconds": round(synthesis_duration, 2),
        "chunks": chunk_metadata,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_text(narrative_metadata_path(session_name), json.dumps(metadata, indent=2) + "\n")
    print(f"Narrative draft written to: {narrative_path(session_name)}")
