from raglib.config import CLEAN
from raglib.io_utils import read_text, write_text


IMPORTANT_TERMS = [
    # Core combat signals
    "initiative",
    "combat",
    "attack",
    "hit",
    "miss",
    "damage",
    "saving throw",
    "save",
    "death",
    "dead",
    "defeated",
    "killed",
    "unconscious",
    "frightened",
    "condition",
    "critical",
    "natural 20",
    "nat 20",

    # Enemies / encounter terms
    "dragon",
    "cultist",
    "cultists",
    "boss",
    "demon",
    "warlock",
    "monster",

    # Spells / abilities
    "eldritch blast",
    "spiritual weapon",
    "fireball",
    "web",
    "cloud of daggers",
    "bardic inspiration",
    "lay on hands",
    "healing word",
    "cure wounds",
    "misty step",
    "shield of faith",
    "sneak attack",
    "riposte",
    "breath weapon",
    "nightmare breath",

    # Campaign terms
    "balrog",
    "well",
    "wells",
    "saiffi",
    "syfie",
    "scythe",
    "wineskin",
    "waterskin",
    "bag of holding",
    "wand of wells",
    "cataclysm",
    "wizard",
    "tower",
    "town square",

    # Party names / likely spellings
    "faban",
    "faben",
    "faven",
    "gildas",
    "mikani",
    "makani",
    "brigit",
    "bridget",
    "corvinas",
    "corvinaus",
    "corvinox",
    "roon",
    "rune",
]


DROP_TERMS = [
    "NO_EVENTS",
    "no useful event",
    "no events",
    "repeated filler",
    "table chatter",
]


def event_blocks(text: str):
    """
    Splits extracted text into EVENT blocks.
    Keeps chunk headings as context when present.
    """
    blocks = []
    current = []

    for line in text.splitlines():
        if line.strip().startswith("EVENT:"):
            if current:
                blocks.append("\n".join(current).strip())
                current = []
        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    return [b for b in blocks if b.strip()]


def score_block(block: str) -> int:
    low = block.lower()
    score = 0

    for term in IMPORTANT_TERMS:
        if term in low:
            score += 1

    if "importance:\nhigh" in low or "importance: high" in low:
        score += 5
    elif "importance:\nmedium" in low or "importance: medium" in low:
        score += 3

    if "confidence:\nhigh" in low or "confidence: high" in low:
        score += 2
    elif "confidence:\nmedium" in low or "confidence: medium" in low:
        score += 1

    return score


def should_drop(block: str) -> bool:
    low = block.lower()

    if any(term.lower() in low for term in DROP_TERMS):
        return True

    if "event_type:" not in low and "summary:" not in low:
        return True

    if score_block(block) < 2:
        return True

    return False


def filter_session(session_name: str):
    input_path = CLEAN / f"{session_name}_events.md"
    output_path = CLEAN / f"{session_name}_filtered.md"

    text = read_text(input_path)
    blocks = event_blocks(text)

    kept = []
    dropped = 0

    for block in blocks:
        if should_drop(block):
            dropped += 1
            continue

        kept.append(block)

    output = [
        "# Filtered Session Events",
        "",
        f"- Source: {input_path.name}",
        f"- Kept events: {len(kept)}",
        f"- Dropped events: {dropped}",
        "",
    ]

    for i, block in enumerate(kept, start=1):
        output.append(f"## Event {i}")
        output.append("")
        output.append(block)
        output.append("")

    write_text(output_path, "\n".join(output))
    print(f"Filtered events written to: {output_path}")
    print(f"Kept: {len(kept)} | Dropped: {dropped}")
