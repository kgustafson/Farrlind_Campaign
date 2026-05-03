import argparse
import re
import subprocess
import sys
from pathlib import Path

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


def sql_quote(value):
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def parse_session_number(path: Path) -> int:
    match = re.search(r"session(\d+)_summary\.md$", path.name)
    if not match:
        raise ValueError(f"Could not parse session number from {path}")
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


def build_sql(summaries: list[dict]) -> str:
    total_events = sum(len(summary["events"]) for summary in summaries)
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

    statements.append(pipeline_run_sql(len(summaries), total_events))
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_SQL.write_text(build_sql(summaries), encoding="utf-8")
    print(f"Wrote {OUT_SQL}")
    print(f"Sessions: {len(summaries)}")
    print(f"Events: {sum(len(summary['events']) for summary in summaries)}")
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
