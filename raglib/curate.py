import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from raglib.config import BASE2, CLEAN, RAW, SESSIONS
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import generate
from raglib.prompts import load_prompt


DEFAULT_MODEL = "gemma4:e2b"
CHUNK_SIZE = 24000
CHUNK_OVERLAP = 1500
OLLAMA_OPTIONS = {
    "temperature": 0.2,
    "top_p": 0.9,
    "num_ctx": 32768,
}


def transcript_path(session_name: str) -> Path:
    return RAW / f"{session_name}_transcript.txt"


def curated_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_curated.md"


def curated_metadata_path(session_name: str) -> Path:
    return CLEAN / f"{session_name}_curated_metadata.json"


def curated_chunks_dir(session_name: str) -> Path:
    return CLEAN / f"{session_name}_curated_chunks"


def session_context_path(session_name: str) -> Path:
    return SESSIONS / f"{session_name}_context.yaml"


def final_summary_path(session_name: str) -> Path:
    match = re.search(r"(\d+)$", session_name)
    if not match:
        return Path()
    previous_number = int(match.group(1)) - 1
    if previous_number < 0:
        return Path()
    return CLEAN.parent / "final" / f"session{previous_number:02d}_summary.md"


def split_transcript(transcript: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks = []
    start = 0
    while start < len(transcript):
        proposed_end = min(start + chunk_size, len(transcript))
        end = proposed_end
        if proposed_end < len(transcript):
            boundary = transcript.rfind("\n\n", start + int(chunk_size * 0.65), proposed_end)
            if boundary != -1:
                end = boundary
        chunk = transcript[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(transcript):
            break
        start = max(0, end - overlap)
    return chunks


def campaign_glossary() -> str:
    return """
- Faban, Mikani, Brigit, Roon, Gildas, Corvinus, Rune: party/member names.
- Catur: underwater city; prefer this over Kator, Couture, Peter, Cater, or similar transcript drift.
- Namaloa: deity/belief associated with Mikani and nature reverence.
- Celestial Isles: draconic/dragonkin society connected to Mikani.
- Korog, Safi / Scythe, Ordor: known wells.
- Wand of Wells: stolen artifact central to the campaign threat.
- Balrog, Paramon, Bentrios, Hanidal, The Gale, Monastery of the Open Hand: known campaign locations.
- Known bad variants to avoid as canon names: Kator, Couture, Peter, Cater, Gildos, Utgar, Namalua, Makani.
""".strip()


def session_context(session_name: str) -> str:
    parts = [f"Session: {session_name}"]
    context_path = session_context_path(session_name)
    if context_path.exists():
        parts.extend(["", "Session context file:", read_text(context_path)])

    previous_summary = final_summary_path(session_name)
    if previous_summary.exists():
        previous = read_text(previous_summary)
        parts.extend([
            "",
            f"Previous session final summary excerpt ({previous_summary.name}):",
            previous[:8000],
        ])

    return "\n".join(parts)


def render_prompt(template_name: str, session_name: str) -> str:
    template = load_prompt(template_name)
    return (
        template
        .replace("{campaign_glossary}", campaign_glossary())
        .replace("{session_context}", session_context(session_name))
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


def build_synthesis_prompt(prompt_text: str, session_name: str, chunk_outputs: list[str]) -> str:
    extracts = []
    for index, output in enumerate(chunk_outputs, start=1):
        extracts.append(f"--- CHUNK EXTRACT {index} START ---\n\n{output.strip()}\n\n--- CHUNK EXTRACT {index} END ---")
    return f"{prompt_text.rstrip()}\n\nSession: {session_name}\n\n" + "\n\n".join(extracts) + "\n"


def canon_scrub(text: str) -> str:
    replacements = {
        r"\bKator\b": "Catur",
        r"\bCouture\b": "Catur",
        r"\bCater\b": "Catur",
        r"\bGildos\b": "Gildas",
        r"\bUtgar\b": "Uthgar",
        r"\bNamalua\b": "Namaloa",
        r"\bMakani\b": "Mikani",
    }
    scrubbed = text
    for pattern, replacement in replacements.items():
        scrubbed = re.sub(pattern, replacement, scrubbed)
    return scrubbed


def curate_session(session_name: str, model: Optional[str] = None) -> None:
    model = model or os.environ.get("FARRLIND_CURATION_MODEL", DEFAULT_MODEL)
    transcript = read_text(transcript_path(session_name))
    chunks = split_transcript(transcript)
    chunks_dir = curated_chunks_dir(session_name)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    chunk_prompt_text = render_prompt("curate_transcript_chunk", session_name)
    synthesis_prompt_text = render_prompt("curate_transcript_synthesis", session_name)

    chunk_outputs = []
    chunk_metadata = []
    total_duration = 0.0

    for index, chunk in enumerate(chunks, start=1):
        print(f"Curating transcript chunk {index} of {len(chunks)} with {model}...")
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
            "output": str(chunk_path.relative_to(BASE2)),
        })

    print(f"Synthesizing curated session packet with {model}...")
    started = time.monotonic()
    final_output = generate(
        build_synthesis_prompt(synthesis_prompt_text, session_name, chunk_outputs),
        model=model,
        timeout=1800,
        options=OLLAMA_OPTIONS,
    ).strip()
    synthesis_duration = time.monotonic() - started
    total_duration += synthesis_duration
    final_output = canon_scrub(final_output)

    write_text(curated_path(session_name), final_output + "\n")
    metadata = {
        "model": model,
        "session": session_name,
        "transcript": str(transcript_path(session_name).relative_to(BASE2)),
        "output": str(curated_path(session_name).relative_to(BASE2)),
        "chunk_count": len(chunks),
        "chunk_size_chars": CHUNK_SIZE,
        "chunk_overlap_chars": CHUNK_OVERLAP,
        "duration_seconds": round(total_duration, 2),
        "synthesis_duration_seconds": round(synthesis_duration, 2),
        "chunks": chunk_metadata,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_text(curated_metadata_path(session_name), json.dumps(metadata, indent=2) + "\n")
    print(f"Curated transcript packet written to: {curated_path(session_name)}")
