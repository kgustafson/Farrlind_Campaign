from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from raglib.config import BASE2, CLEAN, RAW
from raglib.extraction_hygiene import has_any_marker, PARTY_INTERPRETATION_MARKERS, PARTY_FRAMING_MARKERS, WORLD_FACT_MARKERS, normalized_text
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import generate
from raglib.prompts import load_prompt
from raglib.session_spine import normalize_string_list, spine_path


DEFAULT_MODEL = "gemma4:e2b"
OLLAMA_OPTIONS = {
    "temperature": 0.1,
    "top_p": 0.9,
    "num_ctx": 32768,
}
INTERPRETATION_MARKERS = PARTY_INTERPRETATION_MARKERS | PARTY_FRAMING_MARKERS | {
    "resort manager",
}


def narrative_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_narrative.md"


def curated_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_curated.md"


def transcript_path(session_name: str) -> Path:
    return RAW / f"{session_name}_transcript.txt"


def validation_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_spine_validation.md"


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(BASE2))
    except ValueError:
        return str(path)


def load_spine(session_name: str) -> dict[str, Any]:
    document = yaml.safe_load(read_text(spine_path(session_name)))
    if not isinstance(document, dict):
        raise ValueError("Session spine must be a YAML mapping.")
    return document


def text_contains_all(source: str, terms: list[str]) -> bool:
    normalized_source = f" {normalized_text(source)} "
    return all(f" {normalized_text(term)} " in normalized_source for term in terms)


def event_text(event: dict[str, Any]) -> str:
    parts = [
        event.get("title"),
        event.get("event_type"),
        event.get("location"),
        event.get("summary"),
        event.get("outcome"),
        event.get("evidence"),
        event.get("party_interpretation"),
    ]
    for key in ["party_members", "npcs", "entities", "items", "needs_review"]:
        parts.extend(normalize_string_list(event.get(key)))
    return " ".join(str(part or "") for part in parts)


def deterministic_issues(spine: dict[str, Any], source_text: str, narrative: str = "", transcript: str = "") -> dict[str, list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    interpretation: list[str] = []
    location_timeline: list[str] = []

    events = spine.get("major_events") or []
    active_transcript = active_session_transcript(transcript)
    if not events:
        blocking.append("Spine has no major events.")
    orders = [event.get("order") for event in events if isinstance(event, dict)]
    if orders != list(range(1, len(orders) + 1)):
        blocking.append("Major event order values are not contiguous from 1.")

    for event in events:
        if not isinstance(event, dict):
            blocking.append("Major event is not a mapping.")
            continue
        order = event.get("order", "?")
        for key in ["title", "summary", "event_type", "location"]:
            if not str(event.get(key) or "").strip():
                blocking.append(f"Event {order} is missing `{key}`.")
        evidence = str(event.get("evidence") or event.get("summary") or "")
        if evidence and not any(text_contains_all(source_text, [word]) for word in significant_terms(evidence)[:6]):
            warnings.append(f"Event {order} evidence may be weakly supported by source text: {event.get('title')}.")
        if active_transcript:
            event_body = " ".join(str(event.get(key) or "") for key in ["title", "summary", "evidence", "outcome"])
            event_terms = significant_words(event_body)
            transcript_hits = [term for term in event_terms[:10] if text_contains_all(transcript, [term])]
            active_hits = [term for term in event_terms[:10] if text_contains_all(active_transcript, [term])]
            recap_phrases = [
                phrase
                for phrase in phrase_candidates(event_body)
                if text_contains_all(transcript, [phrase]) and not text_contains_all(active_transcript, [phrase])
            ]
            if recap_phrases or (len(transcript_hits) >= 3 and len(active_hits) <= 1 and len(transcript_hits) - len(active_hits) >= 3):
                evidence_hint = f" Recap-only phrase(s): {', '.join(recap_phrases[:3])}." if recap_phrases else ""
                warnings.append(
                    f"Event {order} may be recap/intro contamination rather than active session action: {event.get('title')}.{evidence_hint}"
                )
        objective = " ".join(str(event.get(key) or "") for key in ["title", "summary", "outcome"])
        if has_any_marker(objective, INTERPRETATION_MARKERS) and not has_any_marker(objective, WORLD_FACT_MARKERS):
            interpretation.append(f"Event {order} may present party framing as objective fact: {event.get('title')}.")

    combined_events = " ".join(event_text(event) for event in events if isinstance(event, dict))
    for beat in narrative_beats(narrative):
        beat_terms = significant_words(beat)
        if len(beat_terms) < 3:
            continue
        matched = sum(1 for term in beat_terms if text_contains_all(combined_events, [term]))
        if matched / len(beat_terms) < 0.25:
            missing.append(f"Narrative beat may not be represented in the spine: {beat[:160]}")

    timeline = spine.get("timeline") if isinstance(spine.get("timeline"), dict) else {}
    for key in ["starting_location", "ending_location"]:
        value = str(timeline.get(key) or "").strip()
        if not value:
            location_timeline.append(f"Timeline is missing `{key}`.")
        elif not text_contains_all(source_text, [value]) and value.lower() not in {"n/a", "none identified", "unknown"}:
            location_timeline.append(f"Timeline `{key}` may be weakly supported by source text: {value}.")

    return {
        "blocking": dedupe(blocking),
        "warnings": dedupe(warnings),
        "missing": dedupe(missing),
        "interpretation": dedupe(interpretation),
        "location_timeline": dedupe(location_timeline),
    }


def significant_terms(text: str) -> list[list[str]]:
    words = significant_words(text)
    return [[word] for word in words[:12]]


def significant_words(text: str) -> list[str]:
    stop_words = {
        "about",
        "after",
        "again",
        "before",
        "being",
        "their",
        "there",
        "these",
        "those",
        "through",
        "where",
        "which",
        "while",
    }
    return [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z']+", text.lower())
        if len(word) >= 4 and word not in stop_words
    ]


def phrase_candidates(text: str) -> list[str]:
    ignored = {
        "upon arrival",
        "letter from",
        "from burgomaster",
        "party investigated",
        "party engaged",
        "party traveled",
        "session begins",
    }
    words = significant_words(text)
    phrases: list[str] = []
    for size in (3, 2):
        for index in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[index:index + size])
            if len(phrase) >= 9 and phrase not in ignored:
                phrases.append(phrase)
    return dedupe(phrases)


def narrative_beats(narrative: str) -> list[str]:
    beats: list[str] = []
    in_relevant_section = False
    for raw_line in narrative.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            heading = normalized_text(line)
            in_relevant_section = any(
                marker in heading
                for marker in [
                    "chronological",
                    "major events",
                    "combat",
                    "encounters",
                    "items",
                    "loot",
                    "open threads",
                    "character notes",
                    "timeline",
                ]
            )
            continue
        if not in_relevant_section:
            continue
        if line.startswith(("-", "*")):
            candidate = line.lstrip("-* ").strip()
            if len(significant_words(candidate)) >= 3:
                beats.append(candidate)
    return dedupe(beats)


def active_session_transcript(transcript: str) -> str:
    if not transcript.strip():
        return ""
    markers = [
        "that is where we are now",
        "that is where we are now.",
        "so, you're making your way",
        "so you're making your way",
        "and that is where we are now",
    ]
    lowered = transcript.lower()
    positions = [lowered.find(marker) for marker in markers if lowered.find(marker) != -1]
    if not positions:
        return transcript
    start = min(positions)
    return transcript[start:]


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def deterministic_report(issues: dict[str, list[str]]) -> str:
    lines = ["# Deterministic Precheck", ""]
    for title, key in [
        ("Blocking Issues", "blocking"),
        ("Warnings", "warnings"),
        ("Missing Obvious Beats", "missing"),
        ("Party Interpretation Versus World Fact", "interpretation"),
        ("Location/Timeline Checks", "location_timeline"),
    ]:
        lines.extend([f"## {title}", ""])
        values = issues.get(key) or []
        lines.extend(f"- {value}" for value in values)
        if not values:
            lines.append("- None identified.")
        lines.append("")
    return "\n".join(lines).strip()


def build_validation_prompt(session_name: str, spine: dict[str, Any], deterministic: str, narrative: str, curated: str, transcript: str) -> str:
    template = load_prompt("validate_session_spine")
    transcript_excerpt = active_session_transcript(transcript)[:24000]
    return (
        template.rstrip()
        + f"\n\nSession: {session_name}\n"
        + "\n\n--- DETERMINISTIC PRECHECK START ---\n"
        + deterministic
        + "\n--- DETERMINISTIC PRECHECK END ---\n"
        + "\n\n--- SPINE YAML START ---\n"
        + yaml.safe_dump(spine, sort_keys=False, allow_unicode=True)
        + "--- SPINE YAML END ---\n"
        + "\n\n--- NARRATIVE START ---\n"
        + narrative[:30000]
        + "\n--- NARRATIVE END ---\n"
        + "\n\n--- CURATED PACKET START ---\n"
        + curated[:30000]
        + "\n--- CURATED PACKET END ---\n"
        + "\n\n--- ACTIVE SESSION TRANSCRIPT EXCERPT START ---\n"
        + transcript_excerpt
        + "\n--- ACTIVE SESSION TRANSCRIPT EXCERPT END ---\n"
    )


def validate_session_spine(session_name: str, model: Optional[str] = None) -> None:
    model = model or os.environ.get("FARRLIND_SPINE_VALIDATION_MODEL", DEFAULT_MODEL)
    spine = load_spine(session_name)
    narrative = read_text(narrative_path(session_name))
    curated = read_text(curated_path(session_name)) if curated_path(session_name).exists() else ""
    transcript = read_text(transcript_path(session_name)) if transcript_path(session_name).exists() else ""
    source_text = "\n\n".join([narrative, curated, active_session_transcript(transcript)])
    precheck = deterministic_report(deterministic_issues(spine, source_text, narrative, transcript))
    prompt = build_validation_prompt(session_name, spine, precheck, narrative, curated, transcript)
    print(f"Validating session spine with {model}...")
    started = time.monotonic()
    model_report = generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS).strip()
    duration = time.monotonic() - started
    report = [
        model_report,
        "",
        "---",
        "",
        "## Source Manifest",
        "",
        f"- Spine: {relative(spine_path(session_name))}",
        f"- Narrative: {relative(narrative_path(session_name))}",
        f"- Curated packet: {relative(curated_path(session_name)) if curated_path(session_name).exists() else 'missing'}",
        f"- Transcript: {relative(transcript_path(session_name)) if transcript_path(session_name).exists() else 'missing'}",
        f"- Model: {model}",
        f"- Duration seconds: {round(duration, 2)}",
        f"- Created at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        precheck,
        "",
    ]
    write_text(validation_path(session_name), "\n".join(report))
    print(f"Session spine validation written to: {validation_path(session_name)}")
