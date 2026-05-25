import re
from dataclasses import dataclass
from typing import Optional


RECAP_END_MARKERS = [
    "that is where we are now",
    "that's where we are now",
    "that is where we left off",
    "that's where we left off",
    "and that is where we are now",
    "and that's where we are now",
]
SESSION_END_MARKERS = [
    "that is where we'll end our session",
    "that's where we'll end our session",
    "that is where we will end our session",
    "that's where we will end our session",
    "that is where we'll end it",
    "that's where we'll end it",
    "we'll end our session",
    "we will end our session",
]
POST_SHOW_MARKERS = [
    "if you would like to listen to the short rest",
    "patreon.com slash",
    "patreon.com/",
    "we've got some things to plug",
    "you can follow us on social media",
    "it's time to thank our benevolent council",
    "time to thank our benevolent council",
    "thank our benevolent council of elders",
]
PODCAST_MARKERS = [
    "this episode",
    "episode",
    "i am your",
    "joined as always by",
    "short rest",
    "patreon.com",
    "social media",
    "benevolent council",
    "sponsor",
    "offer ends",
]


@dataclass(frozen=True)
class TranscriptCleanResult:
    text: str
    original_chars: int
    cleaned_chars: int
    start_line: int
    end_line: int
    removed_prefix_lines: int
    removed_suffix_lines: int
    notes: list[str]


def normalized_line(value: str) -> str:
    return re.sub(r"[^a-z0-9']+", " ", value.lower()).strip()


def has_marker(line: str, markers: list[str]) -> bool:
    normalized = normalized_line(line)
    return any(normalized_line(marker) in normalized for marker in markers)


def looks_like_podcast_transcript(lines: list[str]) -> bool:
    sample = "\n".join(lines[: max(1, int(len(lines) * 0.2))])
    sample += "\n" + "\n".join(lines[max(0, int(len(lines) * 0.8)):])
    normalized = normalized_line(sample)
    return any(normalized_line(marker) in normalized for marker in PODCAST_MARKERS)


def find_start_line(lines: list[str]) -> tuple[int, Optional[str]]:
    search_limit = min(len(lines), max(80, int(len(lines) * 0.35)))
    for index, line in enumerate(lines[:search_limit]):
        if has_marker(line, RECAP_END_MARKERS):
            next_line = min(index + 1, len(lines))
            return next_line, "trimmed prefix through recap boundary"
    return 0, None


def find_end_line(lines: list[str], start_line: int) -> tuple[int, Optional[str]]:
    for index in range(start_line, len(lines)):
        if has_marker(lines[index], SESSION_END_MARKERS):
            return index + 1, "trimmed suffix after session-end boundary"

    search_start = max(start_line, int(len(lines) * 0.5))
    for index in range(search_start, len(lines)):
        if has_marker(lines[index], POST_SHOW_MARKERS):
            return index, "trimmed suffix before post-show boundary"
    return len(lines), None


def clean_transcript_for_extraction(text: str) -> TranscriptCleanResult:
    lines = text.splitlines()
    is_podcast = looks_like_podcast_transcript(lines)
    start_line, start_note = find_start_line(lines)
    end_line, end_note = find_end_line(lines, start_line)
    if end_line < start_line:
        end_line = len(lines)

    cleaned_lines = lines[start_line:end_line]
    cleaned = "\n".join(cleaned_lines).strip()
    if cleaned:
        cleaned += "\n"

    notes = [note for note in [start_note, end_note] if note]
    if is_podcast:
        notes.insert(0, "podcast markers detected")
    return TranscriptCleanResult(
        text=cleaned,
        original_chars=len(text),
        cleaned_chars=len(cleaned),
        start_line=start_line + 1 if lines else 0,
        end_line=end_line,
        removed_prefix_lines=start_line,
        removed_suffix_lines=max(0, len(lines) - end_line),
        notes=notes,
    )


def clean_source_text(label: str, text: str) -> str:
    if label != "transcript":
        return text
    return clean_transcript_for_extraction(text).text
