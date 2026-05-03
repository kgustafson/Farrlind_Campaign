import re
from collections import defaultdict

from raglib.config import CLEAN
from raglib.io_utils import read_text, write_text
from raglib.normalize import normalize_key


def is_valid_event(block: str) -> bool:
    """
    Only allow real, well-formed events through.
    """

    low = block.lower()

    # Must have a summary
    if "summary:" not in low:
        return False

    summary = get_field(block, "summary")
    if not summary or len(summary.strip()) < 10:
        return False

    # Must have event_type
    if not get_field(block, "event_type"):
        return False

    # Reject obvious junk blocks
    if "here are the extracted event records" in low:
        return False
    if "extract chunk" in low:
        return False
    if "note:" in low and len(block.splitlines()) < 10:
        return False

    return True

def split_event_blocks(text: str):
    raw_blocks = re.split(r"(?im)^\s*(?:\d+\.\s*)?EVENT\s*:\s*$", text)

    blocks = []
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue

        # Drop prompt/template leftovers
        low = block.lower()
        if (
            "timestamp:" in low
            and "event_type:" in low
            and "summary:" in low
            and not re.search(r"\d{1,2}:\d{2}", block)
        ):
            continue

        blocks.append("EVENT:\n" + block)

    return blocks

def get_field(block: str, field: str) -> str:
    field_variants = {
        "timestamp": ["timestamp"],
        "event_type": ["event_type", "event type"],
        "summary": ["summary"],
        "actors": ["actors"],
        "targets": ["targets", "target"],
        "location": ["location"],
        "mechanical_tags": ["mechanical_tags", "mechanical tags"],
        "story_tags": ["story_tags", "story tags"],
        "outcome": ["outcome"],
        "importance": ["importance"],
        "confidence": ["confidence"],
        "verify": ["verify"],
    }

    labels = [
        "timestamp", "event_type", "event type", "summary", "actors",
        "targets", "target", "location", "mechanical_tags",
        "mechanical tags", "story_tags", "story tags", "outcome",
        "importance", "confidence", "verify"
    ]

    variants = field_variants.get(field, [field])

    for variant in variants:
        pattern = (
            rf"(?im)^\s*{re.escape(variant)}\s*:\s*"
            rf"(.*?)(?=^\s*(?:{'|'.join(re.escape(x) for x in labels)})\s*:|^\s*##\s+Event\b|^\s*#\s+|\Z)"
        )
        match = re.search(pattern, block, re.DOTALL)
        if match:
            return clean_field(match.group(1).strip())

    return ""

def clean_field(value: str) -> str:
    if not value:
        return ""
    if any(x in value.lower() for x in ["targets:", "location:", "mechanical_tags:"]):
        return ""
    return value.strip()

def is_low_value(event):
    summary = event["summary"].lower()

    if len(summary) < 15:
        return True

    if "guy in the back" in summary:
        return True

    if summary.strip() in {"dragon moves.", "wisdom saving throw."}:
        return True

    return False

def event_key(block: str) -> str:
    summary = get_field(block, "summary").lower()
    tags = get_field(block, "mechanical_tags").lower()
    actors = get_field(block, "actors").lower()

    if "initiative" in summary or "initiative" in tags:
        return "combat_start"

    if "nightmare" in summary or "breath" in summary or "breath" in tags:
        return "dragon_breath"

    if "frightened" in summary or "frightened" in tags:
        return "frightened_condition"

    if "cloud of daggers" in summary or "cloud of daggers" in tags:
        return "cloud_of_daggers"

    if "dragon" in summary and ("defeated" in summary or "dead" in summary or "fell" in summary):
        return "dragon_defeat"

    if "eldritch blast" in summary or "eldritch blast" in tags:
        return "eldritch_blast"

    if "wizard" in summary and ("dead" in summary or "defeated" in summary):
        return "wizard_down"

    if "damage" in summary or "damage" in tags:
        return f"damage_{actors[:20]}"

    clean = summary.strip().rstrip(".")

    return clean[:60] if len(clean) > 10 else "minor_event"


def importance_rank(block: str) -> int:
    importance = get_field(block, "importance").lower()

    if "high" in importance:
        return 3
    if "medium" in importance:
        return 2
    if "low" in importance:
        return 1
    return 0

def first_timestamp(event):
    if not event["timestamps"]:
        return "99:99:99"
    return event["timestamps"][0].replace("[", "").replace("]", "")

def get_lane(block: str) -> str:
    """
    Detects the classified lane from nearby section headers.
    Falls back to event_type when no lane header is available.
    """
    low = block.lower()

    if "# combat events" in low:
        return "combat"
    if "# story events" in low:
        return "story"
    if "# lore events" in low:
        return "lore"
    if "# exploration events" in low:
        return "exploration"
    if "# items events" in low:
        return "items"
    if "# character events" in low:
        return "character"
    if "# quest events" in low:
        return "quest"

    event_type = get_field(block, "event_type").lower()

    if event_type in {"combat"}:
        return "combat"
    if event_type in {"roleplay", "decision", "recap"}:
        return "story"
    if event_type == "lore":
        return "lore"
    if event_type in {"exploration", "environment", "travel"}:
        return "exploration"
    if event_type in {"item", "gift", "resource"}:
        return "items"
    if event_type == "character_development":
        return "character"
    if event_type == "quest_objective":
        return "quest"

    return "other"

def merge_blocks(blocks):
    grouped = defaultdict(list)

    for block in blocks:
        lane = get_lane(block)
        raw_key = event_key(block)
        norm_key = normalize_key(raw_key)
        grouped[(lane,norm_key)].append(block)

    merged = []

    for key, group in grouped.items():
        group = sorted(group, key=importance_rank, reverse=True)

        timestamps = []
        summaries = []
        actors = set()
        targets = set()
        locations = set()
        mechanics = set()
        story = set()
        outcomes = []
        verify = []

        max_importance = "low"
        max_confidence = "low"

        for block in group:
            timestamp = get_field(block, "timestamp")
            summary = get_field(block, "summary")
            actor = get_field(block, "actors")
            target = get_field(block, "targets")
            location = get_field(block, "location")
            mech = get_field(block, "mechanical_tags")
            stags = get_field(block, "story_tags")
            outcome = get_field(block, "outcome")
            importance = get_field(block, "importance").lower()
            confidence = get_field(block, "confidence").lower()
            check = get_field(block, "verify")

            if timestamp:
                timestamps.append(timestamp)
            if summary:
                summaries.append(summary)
            if actor:
                actors.add(actor)
            if target:
                targets.add(target)
            if location and location.lower() not in {"unknown", "n/a", "not specified"}:
                locations.add(location)
            if mech:
                mechanics.add(mech)
            if stags:
                story.add(stags)
            if outcome:
                outcomes.append(outcome)
            if check:
                verify.append(check)

            if "high" in importance:
                max_importance = "high"
            elif "medium" in importance and max_importance != "high":
                max_importance = "medium"

            if "high" in confidence:
                max_confidence = "high"
            elif "medium" in confidence and max_confidence != "high":
                max_confidence = "medium"

        if not summaries:
            continue

        merged.append({
            "lane": key[0],
            "key": key[1],
            "timestamps": sorted(set(timestamps)),
            "summary": "; ".join(dict.fromkeys(summaries)),
            "actors": ", ".join(sorted(actors)),
            "targets": ", ".join(sorted(targets)),
            "locations": ", ".join(sorted(locations)) or "Not specified",
            "mechanical_tags": ", ".join(sorted(mechanics)),
            "story_tags": ", ".join(sorted(story)),
            "outcome": "; ".join(dict.fromkeys(outcomes)),
            "importance": max_importance,
            "confidence": max_confidence,
            "verify": "; ".join(dict.fromkeys(verify)),
        })


    merged.sort(key = lambda e: first_timestamp(e))

    return merged


def format_merged_events(events):
    lines = ["# Merged Session Events", ""]

    for i, event in enumerate(events, start=1):
        title = event['key'].replace("_", " ").title()
        lines.extend([
            f"## Event {i}: {title}",
            "",
            f"- timestamps: {', '.join(event['timestamps'])}",
            f"- summary: {event['summary']}",
            f"- actors: {event['actors']}",
            f"- targets: {event['targets']}",
            f"- location: {event['locations']}",
            f"- lane: {event['lane']}",
            f"- mechanical_tags: {event['mechanical_tags']}",
            f"- story_tags: {event['story_tags']}",
            f"- outcome: {event['outcome']}",
            f"- importance: {event['importance']}",
            f"- confidence: {event['confidence']}",
            f"- verify: {event['verify']}",
            "",
        ])

    return "\n".join(lines)


def merge_session(session_name: str):
    input_path = CLEAN / f"{session_name}_normalized.md"
    output_path = CLEAN / f"{session_name}_merged.md"

    text = read_text(input_path)
    blocks = split_event_blocks(text)
    blocks = [b for b in blocks if is_valid_event(b)]
    merged = merge_blocks(blocks)
    output = format_merged_events(merged)

    write_text(output_path, output)

    print(f"Merged events written to: {output_path}")
    print(f"Input events: {len(blocks)} | Merged events: {len(merged)}")
