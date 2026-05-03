import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.config import CLEAN, BASE2
from raglib.summarize import (
    diary_path,
    format_physical_date,
    load_session_metadata,
    optional_read,
    parse_diary_in_game_dates,
    parse_diary_physical_date,
    parse_diary_title,
)


OUT_DIR = BASE2 / "farrlind" / "out"
OUT_SQL = OUT_DIR / "load_summaries.sql"
TRAVEL_FACTS_PATH = BASE2 / "knowledge" / "Faban" / "travel.yaml"

KNOWN_LOCATIONS = [
    "Bentrios",
    "Alexander's Inn",
    "Thataways",
    "Paramon",
    "Balrog",
    "Catur",
    "Gale Monastery",
    "Hanedal Island",
]

TRAVEL_LOCATION_ALIASES = {
    "Alexander's Inn": ["alexander's inn"],
    "Bentrios": ["bentrios"],
    "Thataways": ["thataways", "thisaway", "fey wilds", "fey wild", "feywild"],
    "Paramon": ["paramon"],
    "Balrog": ["balrog"],
    "Catur": ["catur", "sunken city", "catur shoreline"],
    "Gale Monastery": ["gale monastery"],
    "Hanedal Island": ["hanedal", "haunidal", "hanedal island"],
}

KNOWN_NPCS = [
    "Baron Wells",
    "Jennifer",
    "Sam",
]

KNOWN_ENEMIES = [
    "Salazar",
    "Orsydon",
    "Ardema",
    "Iron Paw",
]

KNOWN_ARTIFACTS = [
    "The Black Blade",
    "Grimoire Mutandi",
    "Urgan's Axe",
    "Infernal Orb of Rage",
    "Wand of Wells",
    "Gildas' Enhanced Staff",
    "Mikani's Breathing Cap",
    "Brigit's Upgraded Bow",
    "Corvinas' Flame Blade",
    "Roon's Shield",
]


def sql_quote(value):
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def parse_session_number(path: Path) -> int:
    match = re.search(r"session(\d+)_summary\.md$", path.name)
    if not match:
        raise ValueError(f"Could not parse session number from {path}")
    return int(match.group(1))


def parse_session_ref(value) -> int:
    if isinstance(value, int):
        return value
    match = re.search(r"(\d+)$", str(value))
    if not match:
        raise ValueError(f"Could not parse session reference: {value!r}")
    return int(match.group(1))


def strip_bullet(line: str) -> str:
    return re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()


def parse_summary(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    session_number = parse_session_number(path)
    session_name = f"session{session_number:02d}"
    diary = optional_read(diary_path(session_name))
    metadata = load_session_metadata(session_name)

    physical_date = (
        field_value(text, "Physical Session Date")
        or format_physical_date(metadata)
        or parse_diary_physical_date(diary)
    )
    in_game_date = (
        field_value(text, "In-Game Date")
        or ", ".join(parse_diary_in_game_dates(diary))
    )
    title = (
        field_value(text, "Title")
        or parse_diary_title(diary)
        or f"Session {session_number:02d}"
    )

    key_events = parse_key_events(text)
    summary = parse_prose_summary(text)

    return {
        "session_number": session_number,
        "physical_date": physical_date,
        "in_game_date": in_game_date,
        "title": title,
        "summary": summary,
        "events": key_events,
        "source_path": str(path),
        "location": detect_location(f"{title}\n{summary}\n" + "\n".join(key_events)),
    }


def field_value(text: str, field: str) -> str:
    match = re.search(rf"(?im)^{re.escape(field)}:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def parse_key_events(text: str) -> list[str]:
    match = re.search(r"(?ims)^Key Events:\s*(.*?)(?:^\w[\w ]+:\s*|\Z)", text)
    if not match:
        return []

    events = []
    for line in match.group(1).splitlines():
        event = strip_bullet(line)
        if event:
            events.append(event)

    return events


def parse_prose_summary(text: str) -> str:
    body = re.sub(r"(?im)^Session Summary:\s*", "", text).strip()
    body = re.sub(r"(?im)^Physical Session Date:.*$", "", body)
    body = re.sub(r"(?im)^In-Game Date:.*$", "", body)
    body = re.sub(r"(?im)^Title:.*$", "", body)
    body = re.split(r"(?im)^Key Events:\s*$", body)[0]
    return body.strip()


def detect_location(text: str) -> str:
    low = text.lower()
    for location in KNOWN_LOCATIONS:
        if location.lower() in low:
            return location
    return ""


def location_mentions(text: str) -> list[str]:
    low = text.lower()
    mentions = []

    for location in KNOWN_LOCATIONS:
        aliases = TRAVEL_LOCATION_ALIASES.get(location, [location])
        if any(alias.lower() in low for alias in aliases):
            mentions.append(location)

    return mentions


def detect_travel_method(text: str) -> str:
    low = text.lower()

    if any(term in low for term in ["portal", "transported", "teleport", "dimension door"]):
        return "portal"
    if re.search(r"\b(boat|ship|vessel|sailing)\b", low):
        return "ship"
    if re.search(r"\b(carriage|wagon|cart)\b", low):
        return "wagon"
    if re.search(r"\b(horse|mount|mounts)\b", low):
        return "horse"
    if re.search(r"\b(swim|underwater)\b", low) or any(term in low for term in ["beneath the sea", "descend into the sunken city"]):
        return "swim"

    return "foot"


def detect_duration_days(text: str):
    low = text.lower()
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
    }

    match = re.search(r"\b(\d+)\s+days?\b", low)
    if match:
        return int(match.group(1))

    for word, value in number_words.items():
        if re.search(rf"\b{word}\s+days?\b", low):
            return value

    return None


def extract_travel_logs(summary: dict) -> list[dict]:
    logs = []
    pending_from = ""
    pending_duration = None
    pending_notes = []

    for event in summary["events"]:
        low = event.lower()
        if not any(term in low for term in [
            "travel", "depart", "left", "arrived", "journey", "returned",
            "reached", "headed", "set out", "went to", "transported",
        ]):
            continue

        from_location = ""
        to_location = ""

        explicit_match = re.search(
            r"\bfrom\s+([A-Za-z' ]+?)\s+to\s+([A-Za-z' ]+?)(?:,|\.|$)",
            event,
            re.IGNORECASE,
        )
        if explicit_match:
            from_location = detect_location(explicit_match.group(1))
            to_location = detect_location(explicit_match.group(2))

        depart_match = re.search(r"\bdeparted\s+([A-Za-z' ]+?)(?:\s+with|\s+for|,|$)", event, re.IGNORECASE)
        if depart_match:
            pending_from = detect_location(depart_match.group(1))
            pending_notes = [event]
            pending_duration = detect_duration_days(event)
            continue

        set_out_match = re.search(r"\bset out for\s+([A-Za-z' ]+?)(?:,|\.|$)", event, re.IGNORECASE)
        if set_out_match:
            to_location = detect_location(set_out_match.group(1))
            from_location = summary.get("location", "")

        if "travel" in low and not to_location and not from_location:
            duration = detect_duration_days(event)
            if duration is not None:
                pending_duration = duration
                pending_notes.append(event)
                continue

        return_match = re.search(r"\breturned?\s+(?:to|toward)\s+([A-Za-z' ]+?)(?:,|\.|$)", event, re.IGNORECASE)
        if return_match:
            to_location = detect_location(return_match.group(1))
            from_location = from_location or pending_from or summary.get("location", "")

        arrive_match = re.search(r"\barrived?\s+(?:at|in|on)\s+([A-Za-z' ]+?)(?:,|\.|$)", event, re.IGNORECASE)
        if arrive_match:
            to_location = detect_location(arrive_match.group(1))
            from_location = from_location or pending_from or summary.get("location", "")

        if to_location and from_location != to_location:
            notes = " ".join([*pending_notes, event]).strip()
            logs.append({
                "session_number": summary["session_number"],
                "from_location": from_location,
                "to_location": to_location,
                "travel_method": detect_travel_method(notes),
                "duration_days": pending_duration or detect_duration_days(event),
                "notes": notes,
                "source": "summary",
            })
            pending_from = ""
            pending_duration = None
            pending_notes = []

    return logs


def load_travel_facts() -> list[dict]:
    if not TRAVEL_FACTS_PATH.exists():
        return []

    with open(TRAVEL_FACTS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    logs = []
    for entry in data.get("travel", []) or []:
        logs.append({
            "session_number": parse_session_ref(entry.get("session")),
            "from_location": entry.get("from", ""),
            "to_location": entry.get("to", ""),
            "travel_method": entry.get("method", "foot") or "foot",
            "duration_days": entry.get("duration_days"),
            "notes": entry.get("notes", ""),
            "source": "travel_yaml",
        })

    return logs


def entity_mentioned(entity: str, text: str) -> bool:
    low = text.lower()

    aliases = {
        "The Black Blade": ["black blade", "dark blade"],
        "Grimoire Mutandi": ["grimoire mutandi", "grimoire", "satchel"],
        "Infernal Orb of Rage": ["infernal orb", "orb of rage", "red orb"],
        "Wand of Wells": ["wand of wells"],
        "Gildas' Enhanced Staff": ["enhanced staff", "magical staff", "staff of defense"],
        "Mikani's Breathing Cap": ["breathing cap", "cap of water breathing", "water breathing cap"],
        "Brigit's Upgraded Bow": ["upgraded bow", "magical bow", "bow of warning", "short bow of warning"],
        "Corvinas' Flame Blade": ["flame blade", "flaming longsword", "flaming sword", "flametongue"],
        "Roon's Shield": ["magical shield", "new shield", "shield and armor class"],
    }.get(entity, [entity])

    return any(alias.lower() in low for alias in aliases)


def first_mention_session(entity: str, summaries: list[dict]) -> Optional[int]:
    for summary in summaries:
        text = "\n".join([
            summary["title"],
            summary["summary"],
            *summary["events"],
        ])
        if entity_mentioned(entity, text):
            return summary["session_number"]
    return None


def classify_event_type(event: str) -> str:
    low = event.lower()

    if any(term in low for term in ["combat", "attack", "damage", "defeated", "battle", "cultist"]):
        return "combat"
    if re.search(r"\bdragon\b", low):
        return "combat"
    if any(term in low for term in ["travel", "depart", "road", "journey", "coast", "shoreline"]):
        return "travel"
    if re.search(r"\barrived?\s+(?:at|in|on)\b", low):
        return "travel"
    if any(term in low for term in ["gift", "given", "received", "acquired", "cap", "blade", "bow", "shield", "staff"]):
        return "acquisition"
    if any(term in low for term in ["rest", "long rest", "sleep"]):
        return "rest"
    if any(term in low for term in ["meet", "met", "talk", "asks", "asked", "discuss", "conversation"]):
        return "social"
    if any(term in low for term in ["learn", "discover", "find", "found", "revealed", "well", "wand", "lore"]):
        return "discovery"

    return "discovery"


def event_significance(event: str) -> int:
    low = event.lower()

    if any(term in low for term in ["dragon", "cataclysm", "well", "wand", "demon lord", "defeated"]):
        return 5
    if any(term in low for term in ["gift", "received", "arrived", "learned", "discovered"]):
        return 4
    return 3


def location_expr(location: str) -> str:
    if not location:
        return "NULL"
    return f"(SELECT id FROM location WHERE name = {sql_quote(location)} LIMIT 1)"


def session_sql(session: dict) -> str:
    number = session["session_number"]
    audio_path = BASE2 / "audio" / f"session{number:02d}.wav"
    transcript_path = BASE2 / "knowledge" / "Faban" / "raw" / f"session{number:02d}_transcript.txt"

    return f"""
INSERT INTO session (
    session_number, session_date, in_game_date, title, summary,
    location_id, audio_file_path, transcript_path, notes
)
VALUES (
    {number},
    {sql_quote(session["physical_date"])},
    {sql_quote(session["in_game_date"])},
    {sql_quote(session["title"])},
    {sql_quote(session["summary"])},
    {location_expr(session["location"])},
    {sql_quote(str(audio_path) if audio_path.exists() else "")},
    {sql_quote(str(transcript_path) if transcript_path.exists() else "")},
    {sql_quote("Loaded from " + session["source_path"])}
)
ON CONFLICT (session_number) DO UPDATE SET
    session_date = EXCLUDED.session_date,
    in_game_date = EXCLUDED.in_game_date,
    title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    location_id = EXCLUDED.location_id,
    audio_file_path = EXCLUDED.audio_file_path,
    transcript_path = EXCLUDED.transcript_path,
    notes = EXCLUDED.notes;
""".strip()


def delete_events_sql(session_number: int) -> str:
    return f"""
DELETE FROM session_event
WHERE session_id = (SELECT id FROM session WHERE session_number = {session_number});
""".strip()


def delete_travel_logs_sql(session_number: int) -> str:
    return f"""
DELETE FROM travel_log
WHERE session_id = (SELECT id FROM session WHERE session_number = {session_number})
  AND notes LIKE '%Loaded from summary travel inference%';
""".strip()


def event_sql(session_number: int, sequence: int, event: str) -> str:
    event_type = classify_event_type(event)
    location = detect_location(event)

    return f"""
INSERT INTO session_event (
    session_id, event_type_id, sequence_order, location_id,
    description, significance, notes
)
VALUES (
    (SELECT id FROM session WHERE session_number = {session_number}),
    (SELECT id FROM event_type WHERE type_name = {sql_quote(event_type)}),
    {sequence},
    {location_expr(location)},
    {sql_quote(event)},
    {event_significance(event)},
    {sql_quote("Loaded from summary key event")}
);
""".strip()


def travel_log_sql(log: dict) -> str:
    duration = log["duration_days"] if log["duration_days"] is not None else "NULL"
    if log.get("source") == "travel_yaml":
        notes = f"Loaded from travel.yaml: {log['notes']}"
    else:
        notes = f"Loaded from summary travel inference: {log['notes']}"

    return f"""
INSERT INTO travel_log (
    session_id, from_location_id, to_location_id,
    travel_method, duration_days, notes
)
VALUES (
    (SELECT id FROM session WHERE session_number = {log["session_number"]}),
    {location_expr(log["from_location"])},
    {location_expr(log["to_location"])},
    {sql_quote(log["travel_method"])},
    {duration},
    {sql_quote(notes)}
);
""".strip()


def pipeline_run_sql(session_count: int, event_count: int) -> str:
    return f"""
INSERT INTO pipeline_run (
    pipeline_stage, model_used, input_file, output_file,
    records_created, records_updated, success
)
VALUES (
    'summary_db_load',
    'deterministic-python',
    {sql_quote(str(CLEAN / "session*_summary.md"))},
    {sql_quote(str(OUT_SQL))},
    {session_count + event_count},
    0,
    TRUE
);
""".strip()


def first_seen_sql(summaries: list[dict]) -> str:
    statements = []

    for location in KNOWN_LOCATIONS:
        session_number = first_mention_session(location, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE location "
            f"SET first_visited_session = COALESCE(first_visited_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(location)};"
        )

    for npc in KNOWN_NPCS:
        session_number = first_mention_session(npc, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE npc "
            f"SET first_seen_session = COALESCE(first_seen_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(npc)};"
        )

    for enemy in KNOWN_ENEMIES:
        session_number = first_mention_session(enemy, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE enemy "
            f"SET first_encountered_session = COALESCE(first_encountered_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(enemy)};"
        )

    for artifact in KNOWN_ARTIFACTS:
        session_number = first_mention_session(artifact, summaries)
        if session_number is None:
            continue
        statements.append(
            "UPDATE artifact "
            f"SET discovered_session = COALESCE(discovered_session, (SELECT id FROM session WHERE session_number = {session_number})) "
            f"WHERE name = {sql_quote(artifact)};"
        )

    return "\n".join(statements)


def build_sql(summaries: list[dict]) -> str:
    total_events = sum(len(summary["events"]) for summary in summaries)
    inferred_travel_logs = [
        log
        for summary in summaries
        for log in extract_travel_logs(summary)
    ]
    trusted_travel_logs = load_travel_facts()
    trusted_keys = {
        (log["session_number"], log["from_location"], log["to_location"])
        for log in trusted_travel_logs
    }
    travel_logs = [
        *trusted_travel_logs,
        *[
            log
            for log in inferred_travel_logs
            if (log["session_number"], log["from_location"], log["to_location"]) not in trusted_keys
        ],
    ]
    statements = [
        "-- Generated by scripts/load_summaries.py. Safe to rerun.",
        "BEGIN;",
    ]

    for summary in summaries:
        statements.append(session_sql(summary))

    for summary in summaries:
        statements.append(delete_events_sql(summary["session_number"]))
        for sequence, event in enumerate(summary["events"], start=1):
            statements.append(event_sql(summary["session_number"], sequence, event))

    for summary in summaries:
        statements.append(delete_travel_logs_sql(summary["session_number"]))
    statements.append("DELETE FROM travel_log WHERE notes LIKE '%Loaded from travel.yaml%';")
    for log in travel_logs:
        statements.append(travel_log_sql(log))

    statements.append(first_seen_sql(summaries))
    statements.append(pipeline_run_sql(len(summaries), total_events + len(travel_logs)))
    statements.append("COMMIT;")
    statements.append("")

    return "\n\n".join(statements)


def discover_summaries() -> list[dict]:
    return [
        parse_summary(path)
        for path in sorted(CLEAN.glob("session*_summary.md"))
    ]


def write_sql() -> Path:
    summaries = discover_summaries()
    trusted_travel_logs = load_travel_facts()
    inferred_travel_logs = [
        log
        for summary in summaries
        for log in extract_travel_logs(summary)
    ]
    trusted_keys = {
        (log["session_number"], log["from_location"], log["to_location"])
        for log in trusted_travel_logs
    }
    travel_log_count = len(trusted_travel_logs) + len([
        log
        for log in inferred_travel_logs
        if (log["session_number"], log["from_location"], log["to_location"]) not in trusted_keys
    ])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_SQL.write_text(build_sql(summaries), encoding="utf-8")
    print(f"Wrote {OUT_SQL}")
    print(f"Sessions: {len(summaries)}")
    print(f"Events: {sum(len(summary['events']) for summary in summaries)}")
    print(f"Travel logs: {travel_log_count}")
    return OUT_SQL


def apply_sql(sql_path: Path, container: str, user: str, database: str):
    target = f"/tmp/{sql_path.name}"
    subprocess.run(["docker", "cp", str(sql_path), f"{container}:{target}"], check=True)
    subprocess.run(
        ["docker", "exec", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", database, "-f", target],
        check=True,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Load session summaries into Farrlind Postgres.")
    parser.add_argument("--apply", action="store_true", help="Apply generated SQL through Docker.")
    parser.add_argument("--container", default="farrlind_db")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--database", default="farrlind")
    return parser.parse_args()


def main():
    args = parse_args()
    sql_path = write_sql()

    if args.apply:
        apply_sql(sql_path, args.container, args.user, args.database)


if __name__ == "__main__":
    main()
