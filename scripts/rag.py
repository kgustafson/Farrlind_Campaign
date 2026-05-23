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
from raglib.curate import curate_session
from raglib.npc_extractor import extract_npcs
from raglib.location_extractor import extract_locations
from raglib.artifact_extractor import extract_artifacts
from raglib.lore_item_extractor import extract_lore_items
from raglib.combat_encounter_extractor import extract_combat_encounters
from raglib.open_thread_extractor import extract_open_threads
from scripts.load_summaries import apply_sql, write_sql
from scripts.load_songbook import apply_sql as apply_songbook_sql
from scripts.load_songbook import write_songbook_sql
from scripts.db_backup import backup_database
from scripts.transcribe_parallel import default_audio_path, default_output_path, run_transcription
from raglib.workflow_state import write_historical_workflow_seed_sql, write_workflow_init_sql


STAGES = {
    "curate": curate_session,
    "extract": extract_session,
    "filter": filter_session,
    "classify": classify_session,
    "normalize": normalize_session,
    "merge": merge_session,
    "validate": validate_session,
    "summarize": summarize_session,
    "extract-npcs": extract_npcs,
    "extract-locations": extract_locations,
    "extract-artifacts": extract_artifacts,
    "extract-lore-items": extract_lore_items,
    "extract-combat-encounters": extract_combat_encounters,
    "extract-open-threads": extract_open_threads,
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
    ("audio", REPO_ROOT / "audio", "{session}.wav"),
    ("diary", CLEAN, "{session}_diary.md"),
    ("transcript", RAW, "{session}_transcript.txt"),
    ("curated", CLEAN, "{session}_curated.md"),
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
        choices=[
            *STAGES.keys(),
            "transcribe",
            "postextract",
            "status",
            "dbload",
            "songbook-load",
            "db-backup",
            "workflow-init",
            "workflow-seed-history",
        ],
        help="Workflow command to run.",
    )
    parser.add_argument("session_name", nargs="?", help="Session name, e.g. session20.")
    parser.add_argument("--apply", action="store_true", help="Apply generated database SQL.")
    parser.add_argument("--container", default="farrlind_db", help="Postgres Docker container name.")
    parser.add_argument("--user", default="admin", help="Postgres user.")
    parser.add_argument("--database", default="farrlind", help="Postgres database.")
    parser.add_argument("--backup-output", type=Path, default=None, help="Optional db-backup output path.")
    parser.add_argument("--audio-file", type=Path, default=None, help="Transcribe command input. Defaults to audio/<session>.wav.")
    parser.add_argument("--output", type=Path, default=None, help="Transcribe command output. Defaults to raw/<session>_transcript.txt.")
    parser.add_argument("--model", default=None, help="Model override for commands that support one.")
    parser.add_argument(
        "--source",
        choices=["auto", "final_summary", "curated_packet", "draft_summary", "diary", "transcript"],
        default="auto",
        help="Source material for entity extraction commands. Defaults to auto.",
    )
    parser.add_argument("--chunk-seconds", type=int, default=None, help="Transcribe command chunk size. Defaults to 180.")
    parser.add_argument("--max-workers", type=int, default=None, help="Transcribe command worker count. Defaults to 2.")
    parser.add_argument("--work-dir", type=Path, default=None, help="Optional transcribe command artifact directory.")
    parser.add_argument("--limit-seconds", type=float, default=None, help="Optional transcribe smoke-test limit.")
    parser.add_argument("--start-session", type=int, default=0, help="workflow-seed-history first session number.")
    parser.add_argument("--end-session", type=int, default=20, help="workflow-seed-history final session number.")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "dbload":
        sql_path = write_sql()
        if args.apply:
            apply_sql(sql_path, args.container, args.user, args.database)
        return

    if args.command == "songbook-load":
        sql_path, _report_path, _prompts, _warnings = write_songbook_sql()
        if args.apply:
            apply_songbook_sql(sql_path, args.container, args.user, args.database)
        return

    if args.command == "db-backup":
        backup_path = backup_database(
            args.backup_output,
            container=args.container,
            user=args.user,
            database=args.database,
        )
        print(f"Wrote database backup: {backup_path}")
        print("Restore with:")
        print(
            f"cat {backup_path} | docker exec -i {args.container} "
            f"psql -U {args.user} -d {args.database} -v ON_ERROR_STOP=1"
        )
        return

    if args.command == "workflow-init":
        if not args.session_name:
            raise SystemExit("workflow-init requires a session name, e.g. session21")
        sql_path = write_workflow_init_sql(args.session_name)
        if args.apply:
            apply_sql(sql_path, args.container, args.user, args.database)
        return

    if args.command == "workflow-seed-history":
        sql_path = write_historical_workflow_seed_sql(args.start_session, args.end_session)
        if args.apply:
            apply_sql(sql_path, args.container, args.user, args.database)
        return

    if not args.session_name:
        raise SystemExit(f"{args.command} requires a session name, e.g. session20")

    if args.command == "status":
        print_status(args.session_name)
    elif args.command == "transcribe":
        from raglib.parallel_transcription import DEFAULT_CHUNK_SECONDS, DEFAULT_MAX_WORKERS, DEFAULT_MODEL_SIZE

        args.audio_file = args.audio_file or default_audio_path(args.session_name)
        args.output = args.output or default_output_path(args.session_name)
        args.model = args.model or DEFAULT_MODEL_SIZE
        args.chunk_seconds = args.chunk_seconds or DEFAULT_CHUNK_SECONDS
        args.max_workers = args.max_workers or DEFAULT_MAX_WORKERS
        run_transcription(args)
    elif args.command == "postextract":
        run_stages(args.session_name, POSTEXTRACT_STAGES)
    else:
        if args.command == "extract-npcs":
            extract_npcs(args.session_name, model=args.model, source=args.source)
        elif args.command == "extract-locations":
            extract_locations(args.session_name, model=args.model, source=args.source)
        elif args.command == "extract-artifacts":
            extract_artifacts(args.session_name, model=args.model, source=args.source)
        elif args.command == "extract-lore-items":
            extract_lore_items(args.session_name, model=args.model, source=args.source)
        elif args.command == "extract-combat-encounters":
            extract_combat_encounters(args.session_name, model=args.model, source=args.source)
        elif args.command == "extract-open-threads":
            extract_open_threads(args.session_name, model=args.model, source=args.source)
        else:
            run_stages(args.session_name, [args.command])


if __name__ == "__main__":
    main()
