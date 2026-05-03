from raglib.config import CLEAN, NOTES
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import chat
from raglib.prompts import load_prompt, build_prompt


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


def summarize_session(session_name: str):
    merged = read_text(merged_path(session_name))
    validation = optional_read(validation_path(session_name))
    corrections = optional_read(corrections_path(session_name))

    system_prompt = build_prompt(
        "You are an impartial Dungeons & Dragons campaign archivist.",
        "Your job is to write a factual session summary from structured event records.",
        "Use human correction notes as authoritative when present.",
        "Use validation notes to avoid known transcription errors.",
        "Do not invent events.",
        "Do not write in character voice.",
        "Do not include prompt instructions in the output.",
        "Output ONLY the completed session summary.",
        load_prompt("session_summary"),
    )

    user_prompt = f"""
Create a clean factual session summary for: {session_name}

Use these sources in priority order:

1. HUMAN CORRECTIONS
These override transcription and extraction errors.

{corrections if corrections else "(No human corrections provided.)"}

2. VALIDATION NOTES
These identify possible transcription problems and required topics.

{validation if validation else "(No validation report provided.)"}

3. MERGED EVENT RECORDS
These are the extracted and merged factual events.

{merged}
"""

    result = chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=1200,
    )

    write_text(summary_path(session_name), result.strip() + "\n")

    print(f"Summary written to: {summary_path(session_name)}")
