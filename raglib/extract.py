from raglib.config import RAW, CLEAN
from raglib.io_utils import read_text, write_text
from raglib.chunking import chunk_text
from raglib.prompts import load_prompt, build_prompt
from raglib.ollama_client import chat


def transcript_path(session_name: str):
    return RAW / f"{session_name}_transcript.txt"


def events_path(session_name: str):
    return CLEAN / f"{session_name}_events.md"


def extract_session(session_name: str):
    source = transcript_path(session_name)
    output = events_path(session_name)

    transcript = read_text(source)
    chunks = chunk_text(transcript)

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
Extract event records from this transcript chunk.

Chunk: {index} of {len(chunks)}

TRANSCRIPT CHUNK:
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
