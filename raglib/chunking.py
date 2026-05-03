from typing import List
from raglib.config import CHUNK_MAX_CHARS, CHUNK_OVERLAP


def split_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> List[str]:
    """
    Splits text into chunks without breaking lines mid-sentence when possible.
    """
    lines = text.splitlines()
    chunks = []
    current = []

    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # + newline

        if current_len + line_len > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_len = 0

        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


def add_overlap(chunks: List[str], overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Adds character overlap between chunks to preserve context.
    """
    if overlap <= 0:
        return chunks

    new_chunks = []

    for i, chunk in enumerate(chunks):
        if i == 0:
            new_chunks.append(chunk)
            continue

        prev_chunk = chunks[i - 1]
        overlap_text = prev_chunk[-overlap:]

        combined = overlap_text + "\n" + chunk
        new_chunks.append(combined)

    return new_chunks


def chunk_text(text: str) -> List[str]:
    """
    Full pipeline: split + overlap
    """
    base_chunks = split_text(text)
    return add_overlap(base_chunks)


def debug_chunks(chunks: List[str]):
    for i, chunk in enumerate(chunks, start=1):
        print(f"\n--- Chunk {i} ({len(chunk)} chars) ---")
        print(chunk[:200] + "..." if len(chunk) > 200 else chunk)
