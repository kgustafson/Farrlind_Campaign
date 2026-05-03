import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.config import CLEAN, RAW, SESSIONS
from raglib.extract import extract_session
from raglib.filter_events import filter_session
from raglib.classify_events import classify_session
from raglib.normalize import normalize_session
from raglib.merge import merge_session
from raglib.validate import validate_session
from raglib.summarize import summarize_session
from scripts.load_summaries import apply_sql, write_sql


STAGES = {
    "extract": extract_session,
    "filter": filter_session,
    "classify": classify_session,
    "normalize": normalize_session,
    "merge": merge_session,
    "validate": validate_session,
    "summarize": summarize_session,
}

POSTEXTRACT_STAGES = [
    "filter",
    "classify",
    "normalize",
    "merge",
    "validate",
    "summarize",
]

STATUS_FILES = [
    ("diary", CLEAN, "{session}_diary.md"),
    ("transcript", RAW, "{session}_transcript.txt"),
    ("context", SESSIONS, "{session}_context.yaml"),
    ("events", CLEAN, "{session}_events.md"),
    ("filtered", CLEAN, "{session}_filtered.md"),
    ("classified", CLEAN, "{session}_classified.md"),
    ("normalized", CLEAN, "{session}_normalized.md"),
    ("merged", CLEAN, "{session}_merged.md"),
    ("validation", CLEAN, "{session}_validation.md"),
    ("summary", CLEAN, "{session}_summary.md"),
]


def print_status(session_name: str):
    print(f"Workflow status for {session_name}")
    print("")

    for label, base, pattern in STATUS_FILES:
        path = base / pattern.format(session=session_name)
        marker = "ok" if path.exists() else "missing"
        print(f"{marker:7} {label:11} {path}")


def run_stages(session_name: str, stages: list[str]):
    for stage in stages:
        print(f"\n=== {stage} {session_name} ===")
        STAGES[stage](session_name)


def parse_args():
    parser = argparse.ArgumentParser(
        prog="rag",
        description="Run the local campaign RAG workflow.",
    )
    parser.add_argument(
        "command",
        choices=[*STAGES.keys(), "postextract", "status", "dbload"],
        help="Workflow command to run.",
    )
    parser.add_argument("session_name", nargs="?", help="Session name, e.g. session20.")
    parser.add_argument("--apply", action="store_true", help="Apply generated database SQL.")
    parser.add_argument("--container", default="farrlind_db", help="Postgres Docker container name.")
    parser.add_argument("--user", default="admin", help="Postgres user.")
    parser.add_argument("--database", default="farrlind", help="Postgres database.")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "dbload":
        sql_path = write_sql()
        if args.apply:
            apply_sql(sql_path, args.container, args.user, args.database)
        return

    if not args.session_name:
        raise SystemExit(f"{args.command} requires a session name, e.g. session20")

    if args.command == "status":
        print_status(args.session_name)
    elif args.command == "postextract":
        run_stages(args.session_name, POSTEXTRACT_STAGES)
    else:
        run_stages(args.session_name, [args.command])


if __name__ == "__main__":
    main()
