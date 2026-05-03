from collections import defaultdict
import re

from raglib.config import CLEAN
from raglib.io_utils import read_text, write_text


LANE_MAP = {
    "combat": ["combat"],
    "story": ["roleplay", "decision", "recap"],
    "lore": ["lore"],
    "exploration": ["exploration", "environment", "travel"],
    "items": ["item", "gift", "resource"],
    "character": ["character_development"],
    "quest": ["quest_objective"],
}


def extract_event_blocks(text: str):
    blocks = re.split(r"(?=\nEVENT)", text)
    return [block.strip() for block in blocks if block.strip()]


def get_event_type(block: str) -> str:
    for line in block.splitlines():
        if "event_type" in line.lower():
            return line.split(":")[-1].strip().lower()
    return "unknown"


def classify_session(session_name: str):
    raw_path = CLEAN / f"{session_name}_filtered.md"
    out_path = CLEAN / f"{session_name}_classified.md"

    text = read_text(raw_path)

    lanes = defaultdict(list)

    for block in extract_event_blocks(text):
        if not block.strip():
            continue

        event_type = get_event_type(block)

        placed = False
        for lane, types in LANE_MAP.items():
            if event_type in types:
                lanes[lane].append(block)
                placed = True
                break

        if not placed:
            lanes["other"].append(block)

    output = []

    for lane, events in lanes.items():
        output.append(f"\n\n# {lane.upper()} EVENTS\n")
        output.extend(events)

    write_text(out_path, "\n".join(output))

    print(f"Classified events written to: {out_path}")
