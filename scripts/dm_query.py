import argparse
import csv
import subprocess
import sys
import textwrap
from typing import Optional


DEFAULT_CONTAINER = "farrlind_db"
DEFAULT_USER = "admin"
DEFAULT_DATABASE = "farrlind"


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
    return text[: width - 1].rstrip() + "..."


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


def last_session(args):
    rows = run_query(
        args,
        """
        SELECT s.session_number, s.session_date, s.in_game_date, s.title,
               s.summary, l.name AS location
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
        ORDER BY s.session_number DESC
        LIMIT 1;
        """,
    )
    print_sessions(rows)


def sessions(args):
    rows = run_query(
        args,
        f"""
        SELECT s.session_number, s.session_date, s.in_game_date, s.title,
               s.summary, l.name AS location
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
        ORDER BY s.session_number DESC
        LIMIT {int(args.limit)};
        """,
    )
    print_sessions(rows)


def location(args):
    pattern = like_pattern(args.name)
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
        WHERE COALESCE(el.name, sl.name, '') ILIKE {pattern}
           OR e.description ILIKE {pattern}
        ORDER BY s.session_number, e.sequence_order NULLS LAST, e.id;
        """,
    )
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
        WHERE ({filters})
          AND s.session_number >= (
              SELECT GREATEST(COALESCE(MAX(session_number), 0) - {int(args.recent)}, 0)
              FROM session
          )
        ORDER BY e.significance DESC NULLS LAST, s.session_number DESC, e.sequence_order NULLS LAST
        LIMIT {int(args.limit)};
        """,
    )
    print_events(rows)


def songs(args):
    topic_filter = ""
    if args.topic:
        pattern = like_pattern(args.topic)
        topic_filter = f"""
        WHERE title ILIKE {pattern}
           OR COALESCE(summary, '') ILIKE {pattern}
           OR COALESCE(suno_prompt, '') ILIKE {pattern}
           OR COALESCE(category, '') ILIKE {pattern}
           OR COALESCE(style, '') ILIKE {pattern}
        """
    rows = run_query(
        args,
        f"""
        SELECT song_number, title, style, category, summary, suno_prompt,
               musical_key, meter, tempo
        FROM v_songbook
        {topic_filter}
        ORDER BY song_number
        LIMIT {int(args.limit)};
        """,
    )
    print_songs(rows)


def brief(args):
    topic = args.topic
    print_section(f"{topic.title()} Prep Brief")
    print("")

    print_section("Recent Sessions")
    recent = run_query(
        args,
        """
        SELECT s.session_number, s.session_date, s.in_game_date, s.title,
               s.summary, l.name AS location
        FROM session s
        LEFT JOIN location l ON l.id = s.location_id
        ORDER BY s.session_number DESC
        LIMIT 3;
        """,
    )
    print_sessions(recent, include_summary=False)

    print_section("Topic Events")
    topic_args = argparse.Namespace(**vars(args))
    topic_args.name = topic
    location(topic_args)

    print("")
    print_section("Likely Open Threads")
    thread_args = argparse.Namespace(**vars(args))
    thread_args.recent = 8
    thread_args.limit = 10
    open_threads(thread_args)

    print("")
    print_section("Related Songs")
    song_args = argparse.Namespace(**vars(args))
    song_args.topic = topic
    song_args.limit = 5
    songs(song_args)


def build_parser():
    parser = argparse.ArgumentParser(description="Read-only DM query helper for the Farrlind database.")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--database", default=DEFAULT_DATABASE)

    subparsers = parser.add_subparsers(dest="command", required=True)

    last = subparsers.add_parser("last-session", help="Show the most recent session summary.")
    last.set_defaults(func=last_session)

    recent = subparsers.add_parser("sessions", help="Show recent sessions.")
    recent.add_argument("--limit", type=int, default=5)
    recent.set_defaults(func=sessions)

    loc = subparsers.add_parser("location", help="Show events related to a location or place term.")
    loc.add_argument("name")
    loc.set_defaults(func=location)

    find = subparsers.add_parser("search", help="Search session titles, summaries, and events.")
    find.add_argument("terms", nargs="+")
    find.set_defaults(func=search)

    threads = subparsers.add_parser("open-threads", help="Heuristic list of recent unresolved hooks.")
    threads.add_argument("--recent", type=int, default=8, help="How many sessions back to scan.")
    threads.add_argument("--limit", type=int, default=12)
    threads.set_defaults(func=open_threads)

    song = subparsers.add_parser("songs", help="Show songbook entries, optionally filtered by topic.")
    song.add_argument("topic", nargs="?")
    song.add_argument("--limit", type=int, default=10)
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
