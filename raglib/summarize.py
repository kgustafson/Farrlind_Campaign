import re

from raglib.config import CLEAN, NOTES
from raglib.io_utils import read_text, write_text
from raglib.normalize import load_session_notes
from raglib.ollama_client import chat
from raglib.prompts import load_prompt, build_prompt


MAX_SUMMARY_EVENT_CHARS = 16000

BAD_SUMMARY_PATTERNS = [
    r"\[insert\b",
    r"\[not specified\]",
    r"unspecified date",
    r"unnamed players",
    r"\bdragon,\s*Mikani\b",
    r"\bMikani,\s*with Faban\b",
    r"\bdefeating Mikani\b",
    r"\bMikani was defeated\b",
]

COMMON_WORDS = {
    "about", "after", "again", "against", "their", "there", "these",
    "those", "which", "while", "where", "would", "could", "should",
    "session", "party", "events", "during", "using", "around", "under",
    "through", "toward", "towards",
}


def merged_path(session_name: str):
    return CLEAN / f"{session_name}_merged.md"


def validation_path(session_name: str):
    return CLEAN / f"{session_name}_validation.md"


def corrections_path(session_name: str):
    return NOTES / f"{session_name}_corrections.md"


def summary_path(session_name: str):
    return CLEAN / f"{session_name}_summary.md"


def optional_read(path):
    if path.exists():
        return read_text(path)
    return ""


def extract_context_terms(*texts: str) -> set[str]:
    terms = set()
    for text in texts:
        for word in re.findall(r"[A-Za-z][A-Za-z'-]{4,}", text.lower()):
            if word not in COMMON_WORDS:
                terms.add(word.strip("'"))
    return terms


def split_merged_events(text: str):
    parts = re.split(r"(?m)^## Event\s+(\d+):\s*(.*?)\s*$", text)
    events = []

    for i in range(1, len(parts), 3):
        events.append({
            "sequence": int(parts[i]),
            "title": parts[i + 1].strip(),
            "fields": parse_event_fields(parts[i + 2]),
        })

    return events


def parse_event_fields(body: str) -> dict:
    fields = {}
    current_key = None
    current_value = []

    def flush():
        if current_key:
            fields[current_key] = "\n".join(current_value).strip()

    for line in body.splitlines():
        match = re.match(r"^\s*-\s*([a-z_]+):\s*(.*)$", line)
        if match:
            flush()
            current_key = match.group(1)
            current_value = [match.group(2)]
        elif current_key:
            current_value.append(line)

    flush()
    return fields


def event_score(event: dict, context_terms: set[str]) -> int:
    fields = event["fields"]
    searchable = " ".join([
        event["title"],
        fields.get("summary", ""),
        fields.get("outcome", ""),
        fields.get("location", ""),
        fields.get("mechanical_tags", ""),
        fields.get("story_tags", ""),
    ]).lower()

    score = 0

    importance = fields.get("importance", "").lower()
    if "high" in importance:
        score += 6
    elif "medium" in importance:
        score += 3
    elif "low" in importance:
        score += 1

    confidence = fields.get("confidence", "").lower()
    if "high" in confidence:
        score += 1

    lane = fields.get("lane", "").lower()
    if lane in {"quest", "lore", "items", "exploration", "combat"}:
        score += 2

    matches = sum(1 for term in context_terms if term in searchable)
    score += min(matches, 8) * 3

    return score


def format_event_for_summary(event: dict) -> str:
    fields = event["fields"]
    parts = [
        f"Event {event['sequence']}: {fields.get('summary') or event['title']}",
    ]

    for label in ["location", "lane", "outcome", "mechanical_tags", "story_tags"]:
        value = fields.get(label, "").strip()
        if value:
            parts.append(f"{label}={value}")

    return " | ".join(parts)


def select_events_for_summary(merged: str, context_notes: str, corrections: str) -> str:
    context_terms = extract_context_terms(context_notes, corrections)
    events = split_merged_events(merged)

    scored = [
        (event_score(event, context_terms), event)
        for event in events
    ]

    selected = [
        event
        for score, event in scored
        if score >= 8
    ]

    if len(selected) < 12:
        selected = [
            event
            for _, event in sorted(scored, key=lambda item: item[0], reverse=True)[:24]
        ]

    selected = sorted(selected, key=lambda event: event["sequence"])

    lines = []
    total = 0
    for event in selected:
        line = format_event_for_summary(event)
        if total + len(line) > MAX_SUMMARY_EVENT_CHARS:
            break
        lines.append(line)
        total += len(line)

    return "\n".join(lines)


def summary_has_quality_issue(summary: str) -> bool:
    return any(
        re.search(pattern, summary, re.IGNORECASE)
        for pattern in BAD_SUMMARY_PATTERNS
    )


def context_fallback_summary(context_notes: str) -> str:
    notes = [
        line.strip()
        for line in context_notes.splitlines()
        if line.strip()
    ]

    if not notes:
        return ""

    paragraphs = []
    current = []

    for note in notes:
        current.append(note)
        if len(current) == 3:
            paragraphs.append(" ".join(current))
            current = []

    if current:
        paragraphs.append(" ".join(current))

    key_events = "\n".join(f"- {note.rstrip('.')}" for note in notes)

    return "\n\n".join([
        "Session Summary:",
        "\n\n".join(paragraphs),
        "Key Events:",
        key_events,
    ])


def build_system_prompt(context_notes: str) -> str:
    """
    Builds system prompt with context notes baked in directly.
    Local models respond better to facts in system prompt than user prompt.
    """
    base = [
        "You are a Dungeons & Dragons campaign archivist writing a factual session summary.",
        "You write in clear, factual prose. You do not invent events.",
        "You do not write in character voice.",
        "You do not include prompt instructions in your output.",
        "Output ONLY the completed session summary.",
        "Never output template placeholders.",
        "If a field is unknown, omit it instead of writing that it is unknown.",
        "",
    ]

    if context_notes:
        base += [
            "=== CONFIRMED SESSION FACTS ===",
            "The following events are confirmed true and MUST be included in your summary.",
            "These are not optional. Do not omit any of them.",
            "",
            context_notes.strip(),
            "",
            "=== END CONFIRMED SESSION FACTS ===",
            "",
            "Any extracted event records that contradict the above facts should be ignored.",
            "Any extracted event records that add detail to the above facts may be included.",
            "Build the summary around the confirmed facts before selecting extracted details.",
        ]

    base.append(load_prompt("session_summary"))

    return "\n".join(base)


def summarize_session(session_name: str):
    merged        = read_text(merged_path(session_name))
    validation    = optional_read(validation_path(session_name))
    corrections   = optional_read(corrections_path(session_name))
    context_notes = load_session_notes(session_name)
    summary_events = select_events_for_summary(merged, context_notes, corrections)

    print(f"[summarize] Context notes length: {len(context_notes)} chars")
    print(f"[summarize] Context notes preview: {context_notes[:200]}")

    system_prompt = build_system_prompt(context_notes)

    user_prompt = f"""
Write a session summary for: {session_name}

SUMMARY PRIORITY:
1. Confirmed session facts below and in the system prompt.
2. Human corrections below.
3. Curated extracted event records below.

Treat validation notes as warnings about suspect extracted data. Do not include a validation issue unless it is confirmed by session facts, human corrections, or high-confidence event records.

CONFIRMED SESSION FACTS:
{context_notes if context_notes else "(none)"}

HUMAN CORRECTIONS (treat as ground truth):
{corrections if corrections else "(none)"}

VALIDATION NOTES (flag known transcription errors):
{validation if validation else "(none)"}

CURATED EXTRACTED EVENT RECORDS (use for detail; defer to confirmed facts above):
{summary_events if summary_events else "(none)"}
"""

    result = chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=1200,
    )

    if context_notes and summary_has_quality_issue(result):
        print("[summarize] LLM summary failed quality gate; using context fallback.")
        result = context_fallback_summary(context_notes)

    write_text(summary_path(session_name), result.strip() + "\n")
    print(f"[summarize] Summary written to: {summary_path(session_name)}")
