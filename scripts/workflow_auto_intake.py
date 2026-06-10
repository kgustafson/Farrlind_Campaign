from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_review import db
from web_review.services.workflow import session_key
from raglib import campaign


QUEUE_DIR = REPO_ROOT / "ops" / "workflow_queue"
LOG_DIR = REPO_ROOT / "logs" / "workflow_auto_intake"


@dataclass(frozen=True)
class WorkflowCommand:
    step_id: str
    argv: list[str]
    completed_steps: tuple[str, ...]
    skip_status: str = "not_applicable"
    skip_comment: str = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_name(session_number: int) -> str:
    return session_key(session_number)


def existing_transcript_path(session_number: int) -> Path:
    return campaign.raw_dir() / f"{session_name(session_number)}_transcript.txt"


def normalize_transcript_policy(value: str | None) -> str:
    return "recreate" if (value or "").strip() == "recreate" else "use_existing"


def command_plan(session_number: int, audio_file_path: str = "", transcript_policy: str = "use_existing") -> list[WorkflowCommand]:
    session = session_name(session_number)
    python = sys.executable
    transcribe_command = [python, "scripts/rag.py", "transcribe", session]
    if audio_file_path:
        transcribe_command.extend(["--audio-file", audio_file_path])
    policy = normalize_transcript_policy(transcript_policy)
    transcript_path = existing_transcript_path(session_number)
    if policy == "use_existing" and transcript_path.exists():
        transcribe_command = []
        transcribe_skip_status = "complete"
        transcribe_skip_comment = f"Existing raw transcript preserved; transcription skipped: {transcript_path}"
    else:
        transcribe_skip_status = "not_applicable"
        transcribe_skip_comment = ""
    return [
        WorkflowCommand(
            "transcribe_audio",
            transcribe_command,
            ("transcribe_audio",),
            transcribe_skip_status,
            transcribe_skip_comment,
        ),
        WorkflowCommand(
            "diary_source_available",
            [],
            ("diary_source_available",),
            "not_applicable",
            "No diary source required for audio-first automatic intake.",
        ),
        WorkflowCommand(
            "source_status_check",
            [python, "scripts/rag.py", "status", session],
            ("source_status_check",),
        ),
        WorkflowCommand(
            "curate_transcript",
            [python, "scripts/rag.py", "curate", session],
            ("curate_transcript",),
        ),
        WorkflowCommand(
            "generate_narrative_summary",
            [python, "scripts/rag.py", "generate-narrative-summary", session],
            ("generate_narrative_summary",),
        ),
        WorkflowCommand(
            "extract_session_spine",
            [python, "scripts/rag.py", "extract-session-spine", session],
            ("extract_session_spine",),
        ),
        WorkflowCommand(
            "validate_session_spine",
            [python, "scripts/rag.py", "validate-session-spine", session],
            ("validate_session_spine",),
        ),
        WorkflowCommand(
            "extract_npcs",
            [python, "scripts/rag.py", "extract-npcs", session],
            ("extract_npcs",),
        ),
        WorkflowCommand(
            "extract_locations",
            [python, "scripts/rag.py", "extract-locations", session],
            ("extract_locations",),
        ),
        WorkflowCommand(
            "extract_artifacts",
            [python, "scripts/rag.py", "extract-artifacts", session],
            ("extract_artifacts",),
        ),
        WorkflowCommand(
            "extract_lore_items",
            [python, "scripts/rag.py", "extract-lore-items", session],
            ("extract_lore_items",),
        ),
        WorkflowCommand(
            "extract_combat_encounters",
            [python, "scripts/rag.py", "extract-combat-encounters", session],
            ("extract_combat_encounters",),
        ),
        WorkflowCommand(
            "extract_open_threads",
            [python, "scripts/rag.py", "extract-open-threads", session],
            ("extract_open_threads",),
        ),
        WorkflowCommand(
            "extract_events",
            [python, "scripts/rag.py", "extract", session],
            ("extract_events",),
        ),
        WorkflowCommand(
            "postextract_shortcut",
            [python, "scripts/rag.py", "postextract", session],
            (
                "filter_events",
                "classify_events",
                "normalize_events",
                "merge_events",
                "validate_draft",
                "summarize_draft",
                "postextract_shortcut",
            ),
        ),
    ]


def execute_sql(sql: str, params: dict) -> None:
    engine = db.make_engine()
    with engine.begin() as connection:
        connection.execute(text(sql), params)


def mark_run_running(session_number: int) -> None:
    execute_sql(
        """
        UPDATE workflow_run wr
        SET status = 'running',
            started_at = COALESCE(wr.started_at, NOW()),
            summary_comment = COALESCE(wr.summary_comment || ' ', '') || :summary_comment,
            metadata = wr.metadata || CAST(:metadata AS jsonb)
        FROM session s
        WHERE wr.session_id = s.id
          AND s.session_number = :session_number;
        """,
        {
            "session_number": session_number,
            "summary_comment": "Auto-intake worker started.",
            "metadata": json.dumps({"auto_intake_started_at": utc_now().isoformat()}),
        },
    )


def mark_run_waiting_for_review(session_number: int) -> None:
    execute_sql(
        """
        UPDATE workflow_run wr
        SET status = 'needs_attention',
            summary_comment = COALESCE(wr.summary_comment || ' ', '') || :summary_comment,
            metadata = wr.metadata || CAST(:metadata AS jsonb)
        FROM session s
        WHERE wr.session_id = s.id
          AND s.session_number = :session_number;
        """,
        {
            "session_number": session_number,
            "summary_comment": "Auto-intake completed through draft extraction; waiting for extraction reviews.",
            "metadata": json.dumps({"auto_intake_completed_at": utc_now().isoformat()}),
        },
    )


def mark_run_failed(session_number: int, comment: str) -> None:
    execute_sql(
        """
        UPDATE workflow_run wr
        SET status = 'failed',
            completed_at = NOW(),
            summary_comment = COALESCE(wr.summary_comment || ' ', '') || :summary_comment,
            metadata = wr.metadata || CAST(:metadata AS jsonb)
        FROM session s
        WHERE wr.session_id = s.id
          AND s.session_number = :session_number;
        """,
        {
            "session_number": session_number,
            "summary_comment": comment,
            "metadata": json.dumps({"auto_intake_failed_at": utc_now().isoformat()}),
        },
    )


def mark_step_running(session_number: int, step_id: str, log_path: Path, command: list[str]) -> None:
    execute_sql(
        """
        UPDATE workflow_step_state wss
        SET status = 'running',
            started_at = COALESCE(wss.started_at, NOW()),
            completed_at = NULL,
            summary_comment = :summary_comment,
            metadata = wss.metadata || CAST(:metadata AS jsonb)
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE wss.workflow_run_id = wr.id
          AND s.session_number = :session_number
          AND wss.step_id = :step_id;
        """,
        {
            "session_number": session_number,
            "step_id": step_id,
            "summary_comment": f"Running automatically. Log: {log_path.relative_to(REPO_ROOT)}",
            "metadata": json.dumps({"log_path": str(log_path.relative_to(REPO_ROOT)), "command": command}),
        },
    )


def mark_steps_complete(session_number: int, step_ids: Iterable[str], log_path: Path, comment: str) -> None:
    execute_sql(
        """
        UPDATE workflow_step_state wss
        SET status = 'complete',
            started_at = COALESCE(wss.started_at, NOW()),
            completed_at = NOW(),
            summary_comment = :summary_comment,
            metadata = wss.metadata || CAST(:metadata AS jsonb)
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE wss.workflow_run_id = wr.id
          AND s.session_number = :session_number
          AND wss.step_id = ANY(:step_ids);
        """,
        {
            "session_number": session_number,
            "step_ids": list(step_ids),
            "summary_comment": comment,
            "metadata": json.dumps({"log_path": str(log_path.relative_to(REPO_ROOT))}),
        },
    )


def mark_step_not_applicable(session_number: int, step_id: str, comment: str) -> None:
    execute_sql(
        """
        UPDATE workflow_step_state wss
        SET status = 'not_applicable',
            started_at = COALESCE(wss.started_at, NOW()),
            completed_at = NOW(),
            summary_comment = :summary_comment
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE wss.workflow_run_id = wr.id
          AND s.session_number = :session_number
          AND wss.step_id = :step_id;
        """,
        {"session_number": session_number, "step_id": step_id, "summary_comment": comment},
    )


def mark_step_failed(session_number: int, step_id: str, log_path: Path, returncode: int) -> None:
    execute_sql(
        """
        UPDATE workflow_step_state wss
        SET status = 'failed',
            completed_at = NOW(),
            summary_comment = :summary_comment,
            metadata = wss.metadata || CAST(:metadata AS jsonb)
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE wss.workflow_run_id = wr.id
          AND s.session_number = :session_number
          AND wss.step_id = :step_id;
        """,
        {
            "session_number": session_number,
            "step_id": step_id,
            "summary_comment": f"Automatic step failed with exit code {returncode}. Log: {log_path.relative_to(REPO_ROOT)}",
            "metadata": json.dumps({"log_path": str(log_path.relative_to(REPO_ROOT)), "returncode": returncode}),
        },
    )


def run_command(session_number: int, command: WorkflowCommand, run_dir: Path, dry_run: bool = False) -> None:
    if not command.argv:
        comment = command.skip_comment or "Automatic step skipped."
        log_path = run_dir / f"{command.step_id}.log"
        log_path.write_text(f"{comment}\n", encoding="utf-8")
        if command.skip_status == "complete":
            mark_steps_complete(session_number, command.completed_steps, log_path, comment)
        else:
            mark_step_not_applicable(session_number, command.step_id, comment)
        return

    log_path = run_dir / f"{command.step_id}.log"
    mark_step_running(session_number, command.step_id, log_path, command.argv)
    if dry_run:
        log_path.write_text(f"DRY RUN: {' '.join(command.argv)}\n", encoding="utf-8")
        mark_steps_complete(session_number, command.completed_steps, log_path, f"Dry-run completed. Log: {log_path.relative_to(REPO_ROOT)}")
        return

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"$ {' '.join(command.argv)}\n\n")
        log_file.flush()
        result = subprocess.run(
            command.argv,
            cwd=REPO_ROOT,
            env=os.environ.copy(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if result.returncode != 0:
        mark_step_failed(session_number, command.step_id, log_path, result.returncode)
        raise SystemExit(result.returncode)
    mark_steps_complete(session_number, command.completed_steps, log_path, f"Automatic step completed. Log: {log_path.relative_to(REPO_ROOT)}")


def claim_queue_file(path: Path) -> Path | None:
    running_path = path.with_suffix(".running.json")
    try:
        path.replace(running_path)
    except FileNotFoundError:
        return None
    return running_path


def finish_queue_file(path: Path, suffix: str) -> Path:
    completed_dir = QUEUE_DIR / suffix
    completed_dir.mkdir(parents=True, exist_ok=True)
    target = completed_dir / path.name.replace(".running", "")
    path.replace(target)
    return target


def selected_command_plan(
    session_number: int,
    audio_file_path: str,
    transcript_policy: str,
    selected_steps: list[str] | None = None,
) -> list[WorkflowCommand]:
    plan = command_plan(session_number, audio_file_path, transcript_policy)
    if not selected_steps:
        return plan
    selected = set(selected_steps)
    return [command for command in plan if command.step_id in selected]


def process_job(job_path: Path, dry_run: bool = False) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job_campaign = (job.get("campaign_name") or campaign.active_campaign_name()).strip()
    os.environ["FARRLIND_CAMPAIGN"] = job_campaign
    os.environ["FARRLIND_DATABASE_URL"] = campaign.campaign_database_url(job_campaign)
    session_number = int(job["session_number"])
    audio_file_path = (job.get("audio_file_path") or "").strip()
    transcript_policy = normalize_transcript_policy(job.get("transcript_policy"))
    selected_steps = job.get("commands") if isinstance(job.get("commands"), list) else None
    run_dir = LOG_DIR / session_name(session_number) / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    mark_run_running(session_number)
    try:
        for command in selected_command_plan(session_number, audio_file_path, transcript_policy, selected_steps):
            run_command(session_number, command, run_dir, dry_run=dry_run)
    except SystemExit as exc:
        mark_run_failed(session_number, f"Auto-intake failed before human review. Exit code {exc.code}.")
        finish_queue_file(job_path, "failed")
        raise
    mark_run_waiting_for_review(session_number)
    finish_queue_file(job_path, "done")


def queued_jobs(session_number: int | None = None) -> list[Path]:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    if session_number is not None:
        path = QUEUE_DIR / f"{session_name(session_number)}.json"
        return [path] if path.exists() else []
    return sorted(QUEUE_DIR.glob("session*.json"))


def process_queue(session_number: int | None = None, dry_run: bool = False) -> int:
    jobs = queued_jobs(session_number)
    if not jobs:
        print("No queued workflow intake jobs.")
        return 0
    for path in jobs:
        claimed = claim_queue_file(path)
        if not claimed:
            continue
        print(f"Processing {claimed}")
        process_job(claimed, dry_run=dry_run)
    return 0


def watch_queue(
    session_number: int | None = None,
    dry_run: bool = False,
    poll_seconds: int = 30,
    stop_after: int | None = None,
) -> int:
    poll_seconds = max(1, poll_seconds)
    iterations = 0
    print(f"Watching workflow intake queue every {poll_seconds} seconds.", flush=True)
    while True:
        process_queue(session_number=session_number, dry_run=dry_run)
        iterations += 1
        if stop_after is not None and iterations >= stop_after:
            return 0
        time.sleep(poll_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run queued campaign workflow intake jobs through draft extraction.")
    parser.add_argument("--session", type=int, default=None, help="Only process one session number.")
    parser.add_argument("--dry-run", action="store_true", help="Mark steps without executing commands.")
    parser.add_argument("--watch", action="store_true", help="Keep polling for queued workflow intake jobs.")
    parser.add_argument("--poll-seconds", type=int, default=30, help="Queue polling interval for --watch.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.watch:
        return watch_queue(args.session, dry_run=args.dry_run, poll_seconds=args.poll_seconds)
    return process_queue(args.session, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
