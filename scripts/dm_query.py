import argparse
import csv
import subprocess
import sys
import textwrap
from typing import Optional


DEFAULT_CONTAINER = "farrlind_db"
DEFAULT_USER = "admin"
DEFAULT_DATABASE = "farrlind"
MAX_LIMIT = 1000


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
