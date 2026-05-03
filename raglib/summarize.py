from raglib.config import CLEAN, NOTES
from raglib.io_utils import read_text, write_text
from raglib.normalize import load_session_notes
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
        ]

    base.append(load_prompt("session_summary"))

    return "\n".join(base)


def summarize_session(session_name: str):
    merged        = read_text(merged_path(session_name))
    validation    = optional_read(validation_path(session_name))
    corrections   = optional_read(corrections_path(session_name))
    context_notes = load_session_notes(session_name)

    print(f"[summarize] Context notes length: {len(context_notes)} chars")
    print(f"[summarize] Context notes preview: {context_notes[:200]}")

    system_prompt = build_system_prompt(context_notes)

    user_prompt = f"""
Write a session summary for: {session_name}

HUMAN CORRECTIONS (treat as ground truth):
{corrections if corrections else "(none)"}

VALIDATION NOTES (flag known transcription errors):
{validation if validation else "(none)"}

EXTRACTED EVENT RECORDS (use for detail; defer to confirmed facts above):
{merged}
"""

    result = chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=1200,
    )

    write_text(summary_path(session_name), result.strip() + "\n")
    print(f"[summarize] Summary written to: {summary_path(session_name)}")
