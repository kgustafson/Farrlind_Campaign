import argparse
import csv
import re
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONTAINER = "farrlind_db"
DEFAULT_USER = "admin"
DEFAULT_DATABASE = "farrlind"
MAX_LIMIT = 1000
REPO_ROOT = Path(__file__).resolve().parents[1]
CANON_DECISIONS_PATH = REPO_ROOT / "knowledge" / "Faban" / "canon_decisions.yaml"
REVIEWS_DIR = REPO_ROOT / "knowledge" / "Faban" / "reviews"


def bounded_int(value: str, minimum: int = 1, maximum: int = MAX_LIMIT) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be an integer: {value!r}")
    if number < minimum or number > maximum:
        raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
    return number


def positive_int(value: str) -> int:
    return bounded_int(value)


def parse_session_ref(value: str) -> int:
    match = None
    if value:
        match = re.search(r"(\d+)$", value.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"could not parse session reference: {value!r}")
    return int(match.group(1))


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def like_pattern(value: str) -> str:
    return sql_literal(f"%{value}%")


def run_query(args, sql: str) -> list[dict]:
    command = [
        "docker",
        "exec",
        args.container,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        args.user,
        "-d",
        args.database,
        "--csv",
        "-c",
        sql,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip(), file=sys.stderr)
        raise SystemExit(result.returncode)

    lines = result.stdout.splitlines()
    if not lines:
        return []
    return list(csv.DictReader(lines))


def clip(value: Optional[str], width: int = 220) -> str:
    text = " ".join((value or "").split())
    if len(text) <= width:
        return text
    if width <= 3:
        return "." * width
    return text[: width - 3].rstrip() + "..."


def print_section(title: str):
    print(title)
    print("-" * len(title))


def print_sessions(rows: list[dict], include_summary: bool = True):
    if not rows:
        print("No sessions found.")
        return

    for row in rows:
        heading = f"Session {row['session_number']}: {row.get('title') or 'Untitled'}"
        if row.get("session_date"):
            heading += f" ({row['session_date']})"
        print_section(heading)
        if row.get("location"):
            print(f"Location: {row['location']}")
        if row.get("in_game_date"):
            print(f"In-game: {row['in_game_date']}")
        if include_summary and row.get("summary"):
            print("")
            print(textwrap.fill(clip(row["summary"], 900), width=96))
        print("")


def print_events(rows: list[dict]):
    if not rows:
        print("No events found.")
        return

    current_session = None
    for row in rows:
        session_label = f"Session {row['session_number']}: {row.get('session_title') or 'Untitled'}"
        if session_label != current_session:
            if current_session is not None:
                print("")
            print_section(session_label)
            current_session = session_label
        location = f" [{row['location']}]" if row.get("location") else ""
        event_type = f"{row['event_type']}: " if row.get("event_type") else ""
        print(f"- {event_type}{clip(row['description'], 260)}{location}")


def print_songs(rows: list[dict]):
    if not rows:
        print("No songs found.")
        return

    for row in rows:
        title = f"{row['song_number']}. {row['title']}"
        print_section(title)
        details = [
            row.get("style"),
            row.get("category"),
            row.get("tempo"),
            row.get("meter"),
            row.get("musical_key"),
        ]
        details = [item for item in details if item]
        if details:
            print(" / ".join(details))
        if row.get("summary"):
            print(textwrap.fill(clip(row["summary"], 500), width=96))
        if row.get("suno_prompt"):
            print("")
            print("Prompt:")
            print(textwrap.fill(clip(row["suno_prompt"], 650), width=96))
        print("")


def print_bullets(rows: list[dict], *, empty: str, limit: Optional[int] = None):
    selected = rows[:limit] if limit is not None else rows
    if not selected:
        print(empty)
        return

    for row in selected:
        bits = []
        if row.get("session_number"):
            bits.append(f"S{row['session_number']}")
        if row.get("location"):
            bits.append(row["location"])
        prefix = f" ({', '.join(bits)})" if bits else ""
        event_type = f"{row['event_type']}: " if row.get("event_type") else ""
        print(f"- {event_type}{clip(row.get('description'), 240)}{prefix}")


def print_session_bullets(rows: list[dict], *, empty: str, limit: Optional[int] = None):
    selected = rows[:limit] if limit is not None else rows
    if not selected:
        print(empty)
        return

    for row in selected:
        title = row.get("title") or "Untitled"
        session = row.get("session_number")
        location = f", {row['location']}" if row.get("location") else ""
        print(f"- S{session}: {title}{location} -- {clip(row.get('summary'), 280)}")


def print_prep_questions(topic: str, topic_events: list[dict], open_thread_rows: list[dict]):
    print_section("Prep Questions")

    questions = []
    topic_low = topic.lower()
    direct_text = " ".join(row.get("description") or "" for row in topic_events).lower()
    open_text = " ".join(row.get("description") or "" for row in open_thread_rows).lower()

    if any(word in direct_text for word in ["missing", "underwater", "beneath", "descend", "lights"]):
        questions.append(f"What is the first concrete sign that {topic} is stranger than it looks?")
    if "well" in open_text or "wand" in open_text:
        questions.append("How do the wells, Wand of Wells, or cataclysm pressure the next choice?")
    if topic_low not in open_text and topic_events:
        questions.append(f"Which existing thread should surface first once the party engages with {topic}?")
    questions.extend([
        "What can the party learn without a fight?",
        "What complication should arrive if they hesitate?",
        "Which detail should become canon after the next session?",
    ])

    seen = set()
    for question in questions:
        if question in seen:
            continue
        seen.add(question)
        print(f"- {question}")


def query_recent_sessions(args, limit: int = 3) -> list[dict]:
    return run_query(
        args,
        f"""
        SELECT s.session_number, s.session_date, s.in_game_date, s.title,
               s.summary, l.name AS location
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
        ORDER BY s.session_number DESC
        LIMIT {limit};
        """,
    )


def query_topic_events(args, topic: str, *, direct_only: bool = True, limit: Optional[int] = None) -> list[dict]:
    pattern = like_pattern(topic)
    summary_clause = "" if direct_only else f" OR s.summary ILIKE {pattern} OR s.title ILIKE {pattern}"
    limit_clause = f"LIMIT {limit}" if limit is not None else ""
    return run_query(
        args,
        f"""
        SELECT s.session_number, s.title AS session_title, et.type_name AS event_type,
               COALESCE(el.name, sl.name) AS location, e.description, e.significance
        FROM session_event e
        JOIN session s ON s.id = e.session_id
        LEFT JOIN event_type et ON et.id = e.event_type_id
        LEFT JOIN location el ON el.id = e.location_id
        LEFT JOIN location sl ON sl.id = s.location_id
        WHERE COALESCE(el.name, sl.name, '') ILIKE {pattern}
           OR e.description ILIKE {pattern}
           {summary_clause}
        ORDER BY s.session_number, e.sequence_order NULLS LAST, e.id
        {limit_clause};
        """,
    )


def query_context_sessions(args, topic: str, limit: int = 8) -> list[dict]:
    pattern = like_pattern(topic)
    return run_query(
        args,
        f"""
        SELECT s.session_number, s.session_date, s.in_game_date, s.title,
               s.summary, l.name AS location
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
        WHERE s.title ILIKE {pattern}
           OR s.summary ILIKE {pattern}
           OR s.in_game_date ILIKE {pattern}
        ORDER BY s.session_number DESC
        LIMIT {limit};
        """,
    )


def query_open_threads(args, recent: int = 8, limit: int = 12) -> list[dict]:
    keywords = [
        "open",
        "unresolved",
        "mystery",
        "missing",
        "unknown",
        "preparing",
        "cataclysm",
        "well",
        "wand",
        "beneath",
        "underwater",
    ]
    filters = " OR ".join(f"e.description ILIKE {like_pattern(word)}" for word in keywords)
    return run_query(
        args,
        f"""
        SELECT s.session_number, s.title AS session_title, et.type_name AS event_type,
               COALESCE(el.name, sl.name) AS location, e.description, e.significance
        FROM session_event e
        JOIN session s ON s.id = e.session_id
        LEFT JOIN event_type et ON et.id = e.event_type_id
        LEFT JOIN location el ON el.id = e.location_id
        LEFT JOIN location sl ON sl.id = s.location_id
        WHERE ({filters})
          AND s.session_number >= (
              SELECT GREATEST(COALESCE(MAX(session_number), 0) - {recent}, 0)
              FROM session
          )
        ORDER BY e.significance DESC NULLS LAST, s.session_number DESC, e.sequence_order NULLS LAST
        LIMIT {limit};
        """,
    )


def query_songs(args, topic: Optional[str], limit: int = 10) -> list[dict]:
    topic_filter = ""
    if topic:
        pattern = like_pattern(topic)
        topic_filter = f"""
        WHERE title ILIKE {pattern}
           OR COALESCE(summary, '') ILIKE {pattern}
           OR COALESCE(suno_prompt, '') ILIKE {pattern}
           OR COALESCE(category, '') ILIKE {pattern}
           OR COALESCE(style, '') ILIKE {pattern}
        """
    return run_query(
        args,
        f"""
        SELECT song_number, title, style, category, summary, suno_prompt,
               musical_key, meter, tempo
        FROM v_songbook
        {topic_filter}
        ORDER BY song_number
        LIMIT {limit};
        """,
    )


def query_health(args) -> dict:
    rows = run_query(
        args,
        """
        WITH latest_session AS (
            SELECT session_number, title
            FROM session
            ORDER BY session_number DESC
            LIMIT 1
        ),
        session_counts AS (
            SELECT
                COUNT(*) AS sessions_loaded,
                COUNT(*) FILTER (WHERE summary IS NOT NULL AND summary <> '') AS sessions_with_summaries,
                COUNT(*) FILTER (WHERE transcript_path IS NOT NULL AND transcript_path <> '') AS sessions_with_transcripts,
                STRING_AGG(session_number::TEXT, ', ' ORDER BY session_number)
                    FILTER (WHERE transcript_path IS NOT NULL AND transcript_path <> '') AS transcript_sessions
            FROM session
        ),
        event_counts AS (
            SELECT COUNT(*) AS events_loaded
            FROM session_event
        ),
        song_counts AS (
            SELECT
                COUNT(*) AS songs_loaded,
                COUNT(*) FILTER (WHERE suno_prompt IS NOT NULL AND suno_prompt <> '') AS songs_with_prompts
            FROM song
        ),
        missing_song_prompts AS (
            SELECT STRING_AGG(song_number::TEXT || '. ' || title, '; ' ORDER BY song_number) AS songs_missing_prompts
            FROM song
            WHERE suno_prompt IS NULL OR suno_prompt = ''
        ),
        primary_location_mismatches AS (
            SELECT STRING_AGG(
                'Session ' || s.session_number::TEXT || ' primary location is ' ||
                COALESCE(sl.name, 'unset') || ', but event locations include ' ||
                event_locations.event_location_names,
                '; '
                ORDER BY s.session_number
            ) AS notes
            FROM session s
            LEFT JOIN location sl ON sl.id = s.location_id
            JOIN LATERAL (
                SELECT STRING_AGG(DISTINCT el.name, ', ' ORDER BY el.name) AS event_location_names
                FROM session_event e
                JOIN location el ON el.id = e.location_id
                WHERE e.session_id = s.id
                  AND (s.location_id IS NULL OR e.location_id <> s.location_id)
            ) event_locations ON event_locations.event_location_names IS NOT NULL
        )
        SELECT
            session_counts.sessions_loaded,
            session_counts.sessions_with_summaries,
            session_counts.sessions_with_transcripts,
            COALESCE(session_counts.transcript_sessions, '') AS transcript_sessions,
            event_counts.events_loaded,
            song_counts.songs_loaded,
            song_counts.songs_with_prompts,
            (song_counts.songs_loaded - song_counts.songs_with_prompts) AS songs_missing_prompt_count,
            COALESCE(missing_song_prompts.songs_missing_prompts, '') AS songs_missing_prompts,
            latest_session.session_number AS latest_session_number,
            latest_session.title AS latest_session_title,
            COALESCE(primary_location_mismatches.notes, '') AS location_mismatch_notes
        FROM session_counts
        CROSS JOIN event_counts
        CROSS JOIN song_counts
        CROSS JOIN missing_song_prompts
        CROSS JOIN latest_session
        CROSS JOIN primary_location_mismatches;
        """,
    )
    return rows[0] if rows else {}


def query_event_review(args, session_number: int) -> dict:
    sessions = run_query(
        args,
        f"""
        SELECT s.session_number, s.session_date, s.in_game_date, s.title,
               s.summary, l.name AS location
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
        WHERE s.session_number = {session_number}
        LIMIT 1;
        """,
    )
    events = run_query(
        args,
        f"""
        SELECT s.session_number, s.title AS session_title, et.type_name AS event_type,
               COALESCE(el.name, sl.name) AS location, e.sequence_order,
               e.description, e.significance
        FROM session_event e
        JOIN session s ON s.id = e.session_id
        LEFT JOIN event_type et ON et.id = e.event_type_id
        LEFT JOIN location el ON el.id = e.location_id
        LEFT JOIN location sl ON sl.id = s.location_id
        WHERE s.session_number = {session_number}
        ORDER BY e.sequence_order NULLS LAST, e.id;
        """,
    )
    return {
        "session": sessions[0] if sessions else {},
        "events": events,
    }


def split_notes(value: Optional[str]) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def load_canon_decisions(path: Path = CANON_DECISIONS_PATH) -> dict:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def format_canon_decisions(decisions: dict) -> list[str]:
    notes = []

    for item in decisions.get("session_primary_locations", []) or []:
        session = item.get("session", "unknown session")
        canonical = item.get("canonical", "unknown location")
        status = item.get("status", "unknown")
        decision = item.get("decision") or f"Primary location is {canonical}."
        notes.append(f"{session} primary location -> {canonical} [{status}]: {decision}")

    for item in decisions.get("event_review_decisions", []) or []:
        session = item.get("session", "unknown session")
        status = item.get("status", "unknown")
        decision_type = item.get("decision_type", "event_review")
        description = clip(item.get("description"), 180)
        notes.append(f"{session} {decision_type} [{status}]: {description}")

    return notes


def canon_primary_location_session_numbers(decisions: dict) -> set[int]:
    sessions = set()
    for item in decisions.get("session_primary_locations", []) or []:
        try:
            sessions.add(parse_session_ref(item.get("session", "")))
        except argparse.ArgumentTypeError:
            continue
    return sessions


def note_session_number(note: str) -> Optional[int]:
    match = re.search(r"\bSession\s+(\d+)\b", note or "")
    return int(match.group(1)) if match else None


def session_key(session_number: int) -> str:
    return f"session{session_number:02d}"


def review_path(session_number: int) -> Path:
    return REVIEWS_DIR / f"{session_key(session_number)}_review.yaml"


def load_review_file(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def discover_review_files(path: Path = REVIEWS_DIR) -> list[Path]:
    if not path.exists():
        return []
    return sorted(path.glob("*_review.yaml"))


def summarize_review(document: dict, path: Optional[Path] = None) -> dict:
    items = list(document.get("items") or [])
    added_items = list(document.get("added_items") or [])
    all_items = [*items, *added_items]
    decisions = {
        "pending": 0,
        "accepted": 0,
        "rejected": 0,
        "corrected": 0,
        "added": 0,
        "other": 0,
    }
    applied = {
        "pending": 0,
        "applied": 0,
        "other": 0,
    }

    for item in all_items:
        decision = item.get("decision") or "pending"
        decisions[decision if decision in decisions else "other"] += 1
        applied_status = item.get("applied_status") or "pending"
        applied[applied_status if applied_status in applied else "other"] += 1

    return {
        "session": document.get("session") or (path.stem.replace("_review", "") if path else "unknown"),
        "status": document.get("status") or "unknown",
        "title": document.get("session_title") or "",
        "path": str(path) if path else "",
        "total_items": len(all_items),
        "base_items": len(items),
        "added_items": len(added_items),
        "decisions": decisions,
        "applied": applied,
    }


def review_has_pending_decisions(document: dict) -> bool:
    summary = summarize_review(document)
    return summary["decisions"]["pending"] > 0


def review_next_action(summary: dict) -> tuple[str, str]:
    decisions = summary["decisions"]
    applied = summary["applied"]
    session = summary["session"]
    status = summary["status"]

    if decisions["pending"] or decisions["other"]:
        issue_bits = []
        if decisions["pending"]:
            issue_bits.append(f"{decisions['pending']} pending")
        if decisions["other"]:
            issue_bits.append(f"{decisions['other']} unknown")
        return "edit", f"Edit {summary['path']} ({', '.join(issue_bits)} decisions)."

    if status in {"reviewed", "complete"} and applied["pending"]:
        return "apply", f"Run: ./rag-env/bin/python scripts/dm_query.py apply-review {session}"

    if status == "in_review":
        return "mark-reviewed", f"Set top-level status: reviewed in {summary['path']}."

    if status == "applied" and applied["pending"] == 0 and applied["other"] == 0:
        return "done", "Review is applied."

    if applied["other"]:
        return "inspect", f"Inspect applied_status values in {summary['path']}."

    return "inspect", f"Inspect review status '{status}' in {summary['path']}."


def mark_review_applied(document: dict, applied_on: str) -> dict:
    document = {**document, "status": "applied", "applied_on": applied_on}
    for section in ["items", "added_items"]:
        updated = []
        for item in document.get(section) or []:
            item = {**item}
            if item.get("decision") in {"accepted", "rejected", "corrected", "added"}:
                item["applied_status"] = "applied"
                item["applied_on"] = applied_on
            updated.append(item)
        document[section] = updated
    return document


def save_review_file(path: Path, document: dict):
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def canon_decisions_for_session(decisions: dict, session_number: int) -> dict:
    key = session_key(session_number)
    return {
        "session_primary_locations": [
            item for item in decisions.get("session_primary_locations", []) or []
            if item.get("session") == key
        ],
        "event_review_decisions": [
            item for item in decisions.get("event_review_decisions", []) or []
            if item.get("session") == key
        ],
    }


def review_item_from_event(event: dict) -> dict:
    sequence = event.get("sequence_order") or "0"
    try:
        sequence_number = int(sequence)
    except ValueError:
        sequence_number = 0

    return {
        "id": f"event-{sequence_number:03d}",
        "source_type": "db_event",
        "source_text": event.get("description") or "",
        "decision": "pending",
        "canonical_text": "",
        "event_type": event.get("event_type") or "",
        "location": event.get("location") or "",
        "significance": int(event["significance"]) if event.get("significance") else None,
        "reason": "",
        "decided_by": "",
        "decided_on": "",
        "applied_status": "pending",
        "applied_on": "",
    }


def build_review_document(session: dict, events: list[dict]) -> dict:
    session_number = int(session["session_number"])
    return {
        "session": session_key(session_number),
        "status": "in_review",
        "review_instructions": [
            "For each item, set decision to accepted, rejected, corrected, or added.",
            "For corrected or added items, fill canonical_text and any changed metadata.",
            "Leave applied_status as pending until an apply-review step updates the database.",
        ],
        "session_title": session.get("title") or "",
        "session_date": str(session.get("session_date") or ""),
        "in_game_date": session.get("in_game_date") or "",
        "primary_location": session.get("location") or "",
        "items": [review_item_from_event(event) for event in events],
        "added_items": [],
    }


def last_session(args):
    rows = query_recent_sessions(args, limit=1)
    print_sessions(rows)


def sessions(args):
    rows = query_recent_sessions(args, limit=args.limit)
    print_sessions(rows)


def location(args):
    rows = query_topic_events(args, args.name, direct_only=True)
    print_events(rows)


def search(args):
    terms = [term for term in args.terms if term.strip()]
    if not terms:
        raise SystemExit("search requires at least one term")

    event_filters = " AND ".join(
        f"(e.description ILIKE {like_pattern(term)} OR s.summary ILIKE {like_pattern(term)} OR s.title ILIKE {like_pattern(term)})"
        for term in terms
    )
    rows = run_query(
        args,
        f"""
        SELECT s.session_number, s.title AS session_title, et.type_name AS event_type,
               COALESCE(el.name, sl.name) AS location, e.description
        FROM session_event e
        JOIN session s ON s.id = e.session_id
        LEFT JOIN event_type et ON et.id = e.event_type_id
        LEFT JOIN location el ON el.id = e.location_id
        LEFT JOIN location sl ON sl.id = s.location_id
        WHERE {event_filters}
        ORDER BY s.session_number, e.sequence_order NULLS LAST, e.id;
        """,
    )
    print_events(rows)


def open_threads(args):
    rows = query_open_threads(args, recent=args.recent, limit=args.limit)
    print_events(rows)


def songs(args):
    rows = query_songs(args, args.topic, limit=args.limit)
    print_songs(rows)


def health(args):
    row = query_health(args)
    canon_decisions = load_canon_decisions()
    canon_notes = format_canon_decisions(canon_decisions)
    canon_primary_sessions = canon_primary_location_session_numbers(canon_decisions)
    if not row:
        print("No health data found.")
        if canon_notes:
            print("")
            print_section("Canon Decisions")
            for note in canon_notes:
                print(f"- {note}")
        return

    print_section("DM Query Health")
    print(f"Sessions loaded: {row['sessions_loaded']}")
    print(f"Sessions with summaries: {row['sessions_with_summaries']}")
    print(f"Events loaded: {row['events_loaded']}")
    print(f"Songs loaded: {row['songs_loaded']}")
    print(f"Songs with prompts: {row['songs_with_prompts']}")
    print(f"Songs missing prompts: {row['songs_missing_prompt_count']}")
    print(
        "Latest session: "
        f"{row['latest_session_number']} - {row.get('latest_session_title') or 'Untitled'}"
    )
    transcript_sessions = row.get("transcript_sessions") or "none"
    print(f"Sessions with transcripts: {transcript_sessions}")
    print("")

    print_section("Data Notes")
    notes = []
    for song in split_notes(row.get("songs_missing_prompts")):
        notes.append(f"Song missing prompt: {song}")
    for note in split_notes(row.get("location_mismatch_notes")):
        session_number = note_session_number(note)
        if session_number in canon_primary_sessions:
            continue
        notes.append(note)

    if not notes:
        print("No obvious data notes.")
        return
    for note in notes:
        print(f"- {note}")

    print("")
    print_section("Canon Decisions")
    if not canon_notes:
        print("No canon decisions recorded.")
        return
    for note in canon_notes:
        print(f"- {note}")


def review_events(args):
    session_number = args.session_number
    review = query_event_review(args, session_number)
    session = review["session"]
    decisions = canon_decisions_for_session(load_canon_decisions(), session_number)

    print_section(f"Session {session_number:02d} Event Review")
    if not session:
        print("No session found.")
        return

    title = session.get("title") or "Untitled"
    print(f"Title: {title}")
    if session.get("session_date"):
        print(f"Physical date: {session['session_date']}")
    if session.get("in_game_date"):
        print(f"In-game: {session['in_game_date']}")
    if session.get("location"):
        print(f"Primary location: {session['location']}")
    print("")

    print_section("Source Summary")
    print(textwrap.fill(clip(session.get("summary"), 1200), width=96))
    print("")

    print_section("Current DB Events")
    if not review["events"]:
        print("No DB events found.")
    else:
        for event in review["events"]:
            sequence = event.get("sequence_order") or "?"
            event_type = f"{event['event_type']}: " if event.get("event_type") else ""
            location = f" [{event['location']}]" if event.get("location") else ""
            significance = f" significance={event['significance']}" if event.get("significance") else ""
            print(f"{sequence}. {event_type}{clip(event.get('description'), 320)}{location}{significance}")
    print("")

    print_section("Canon Location Decisions")
    primary_locations = decisions["session_primary_locations"]
    if not primary_locations:
        print("No location decisions recorded for this session.")
    for item in primary_locations:
        print(f"- {item.get('canonical', 'unknown location')} [{item.get('status', 'unknown')}]: {item.get('decision', '')}")
    print("")

    print_section("Canon Event Decisions")
    event_decisions = decisions["event_review_decisions"]
    if not event_decisions:
        print("No event decisions recorded for this session.")
    for item in event_decisions:
        print(f"- {item.get('event_type', 'event')} significance={item.get('significance', '?')} [{item.get('status', 'unknown')}]")
        print(textwrap.fill(item.get("description", ""), width=96, initial_indent="  ", subsequent_indent="  "))
        notes = item.get("canon_notes") or []
        for note in notes:
            print(f"  - {note}")


def init_review(args):
    session_number = args.session_number
    output_path = review_path(session_number)
    if output_path.exists():
        raise SystemExit(f"Review file already exists: {output_path}")

    review = query_event_review(args, session_number)
    session = review["session"]
    if not session:
        raise SystemExit(f"No session found for session{session_number:02d}")

    document = build_review_document(session, review["events"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    print(f"Items: {len(document['items'])}")


def review_status(args):
    files = discover_review_files()
    print_section("Review Status")
    if not files:
        print("No review files found.")
        return

    for path in files:
        summary = summarize_review(load_review_file(path), path)
        print(f"{summary['session']}: {summary['status']}")
        if summary["title"]:
            print(f"  title: {summary['title']}")
        print(f"  file: {summary['path']}")
        print(f"  items: {summary['total_items']} ({summary['base_items']} drafted, {summary['added_items']} added)")
        decisions = summary["decisions"]
        print(
            "  decisions: "
            f"pending={decisions['pending']}, "
            f"accepted={decisions['accepted']}, "
            f"rejected={decisions['rejected']}, "
            f"corrected={decisions['corrected']}, "
            f"added={decisions['added']}, "
            f"other={decisions['other']}"
        )
        applied = summary["applied"]
        print(
            "  applied: "
            f"pending={applied['pending']}, "
            f"applied={applied['applied']}, "
            f"other={applied['other']}"
        )


def review_next(args):
    paths = [review_path(args.session_number)] if args.session_number else discover_review_files()
    print_section("Review Next")
    if args.session_number and not paths[0].exists():
        session = session_key(args.session_number)
        print(f"{session}: init")
        print(f"  Run: ./rag-env/bin/python scripts/dm_query.py init-review {session}")
        return
    if not paths:
        print("No review files found.")
        print("  Run init-review after a session has been loaded into the database.")
        return

    for path in paths:
        if not path.exists():
            continue
        summary = summarize_review(load_review_file(path), path)
        action, detail = review_next_action(summary)
        print(f"{summary['session']}: {action}")
        if summary["title"]:
            print(f"  title: {summary['title']}")
        print(f"  {detail}")


def apply_review(args):
    session_number = args.session_number
    path = review_path(session_number)
    if not path.exists():
        raise SystemExit(f"Review file does not exist: {path}")

    document = load_review_file(path)
    if review_has_pending_decisions(document):
        raise SystemExit(f"Review has pending decisions: {path}")
    if document.get("status") not in {"reviewed", "complete", "applied"}:
        raise SystemExit(
            f"Review status must be reviewed, complete, or applied before DB update: {document.get('status')}"
        )

    command = [sys.executable, "scripts/rag.py", "dbload", "--apply"]
    result = subprocess.run(command, cwd=REPO_ROOT, check=False, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    applied_on = args.applied_on or date.today().isoformat()
    save_review_file(path, mark_review_applied(document, applied_on))
    print(f"Applied review: {path}")


def brief(args):
    topic = args.topic
    print_section(f"{topic.title()} Prep Brief")
    print("")

    recent = query_recent_sessions(args, limit=3)
    topic_events = query_topic_events(args, topic, direct_only=True)
    context_sessions = query_context_sessions(args, topic, limit=8)
    open_thread_rows = query_open_threads(args, recent=8, limit=10)
    related_songs = query_songs(args, topic, limit=5)

    print_section("Direct Topic Facts")
    print_bullets(topic_events, empty=f"No direct events found for {topic}.")
    print("")

    print_section("Recent Campaign Context")
    print_sessions(recent, include_summary=False)

    print_section("Broader Topic Context")
    print_session_bullets(context_sessions, empty=f"No broader context found for {topic}.", limit=8)
    print("")

    print_section("Open Threads")
    print_bullets(open_thread_rows, empty="No likely open threads found.", limit=8)
    print("")

    print_prep_questions(topic, topic_events, open_thread_rows)
    print("")

    print_section("Related Songs")
    print_songs(related_songs)


def build_parser():
    parser = argparse.ArgumentParser(description="Read-only DM query helper for the Farrlind database.")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--database", default=DEFAULT_DATABASE)

    subparsers = parser.add_subparsers(dest="command", required=True)

    last = subparsers.add_parser("last-session", help="Show the most recent session summary.")
    last.set_defaults(func=last_session)

    recent = subparsers.add_parser("sessions", help="Show recent sessions.")
    recent.add_argument("--limit", type=positive_int, default=5)
    recent.set_defaults(func=sessions)

    loc = subparsers.add_parser("location", help="Show events related to a location or place term.")
    loc.add_argument("name")
    loc.set_defaults(func=location)

    find = subparsers.add_parser("search", help="Search session titles, summaries, and events.")
    find.add_argument("terms", nargs="+")
    find.set_defaults(func=search)

    threads = subparsers.add_parser("open-threads", help="Heuristic list of recent unresolved hooks.")
    threads.add_argument("--recent", type=positive_int, default=8, help="How many sessions back to scan.")
    threads.add_argument("--limit", type=positive_int, default=12)
    threads.set_defaults(func=open_threads)

    song = subparsers.add_parser("songs", help="Show songbook entries, optionally filtered by topic.")
    song.add_argument("topic", nargs="?")
    song.add_argument("--limit", type=positive_int, default=10)
    song.set_defaults(func=songs)

    status = subparsers.add_parser("health", help="Show database loading and data-quality health.")
    status.set_defaults(func=health)

    review = subparsers.add_parser("review-events", help="Review DB events and pending canon decisions for a session.")
    review.add_argument("session_number", type=parse_session_ref, help="Session number or name, e.g. 20 or session20.")
    review.set_defaults(func=review_events)

    init = subparsers.add_parser("init-review", help="Create a draft YAML review file for a session.")
    init.add_argument("session_number", type=parse_session_ref, help="Session number or name, e.g. 20 or session20.")
    init.set_defaults(func=init_review)

    review_status_parser = subparsers.add_parser("review-status", help="Show status counts for YAML session review files.")
    review_status_parser.set_defaults(func=review_status)

    review_next_parser = subparsers.add_parser("review-next", help="Show the next review workflow action.")
    review_next_parser.add_argument("session_number", nargs="?", type=parse_session_ref, help="Optional session number or name.")
    review_next_parser.set_defaults(func=review_next)

    apply = subparsers.add_parser("apply-review", help="Apply a completed review through the durable DB load path.")
    apply.add_argument("session_number", type=parse_session_ref, help="Session number or name, e.g. 20 or session20.")
    apply.add_argument("--applied-on", default="", help="Applied date to record in review YAML, e.g. YYYY-MM-DD.")
    apply.set_defaults(func=apply_review)

    prep = subparsers.add_parser("brief", help="Build a compact prep brief around a topic.")
    prep.add_argument("topic")
    prep.set_defaults(func=brief)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
