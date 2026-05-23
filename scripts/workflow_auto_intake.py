from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
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


QUEUE_DIR = REPO_ROOT / "ops" / "workflow_queue"
LOG_DIR = REPO_ROOT / "logs" / "workflow_auto_intake"


@dataclass(frozen=True)
class WorkflowCommand:
    step_id: str
    argv: list[str]
    completed_steps: tuple[str, ...]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_name(session_number: int) -> str:
    return session_key(session_number)


def command_plan(session_number: int) -> list[WorkflowCommand]:
    session = session_name(session_number)
    python = sys.executable
    return [
        WorkflowCommand(
            "transcribe_audio",
            [python, "scripts/rag.py", "transcribe", session],
            ("transcribe_audio",),
        ),
        WorkflowCommand(
            "diary_source_available",
            [],
            ("diary_source_available",),
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
        WorkflowCommand(
            "initialize_review",
            [python, "scripts/dm_query.py", "init-review", session],
            ("initialize_review",),
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
            "summary_comment": "Auto-intake completed through init-review; waiting for human review.",
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
        mark_step_not_applicable(
            session_number,
            command.step_id,
            "No diary source required for audio-first automatic intake.",
        )
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


def process_job(job_path: Path, dry_run: bool = False) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    session_number = int(job["session_number"])
    run_dir = LOG_DIR / session_name(session_number) / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    mark_run_running(session_number)
    try:
        for command in command_plan(session_number):
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run queued Farrlind workflow intake jobs through init-review.")
    parser.add_argument("--session", type=int, default=None, help="Only process one session number.")
    parser.add_argument("--dry-run", action="store_true", help="Mark steps without executing commands.")
    return parser.parse_args()


def main() -> int:
    os.environ.setdefault("FARRLIND_DATABASE_URL", "postgresql+psycopg2://admin:gofaban@localhost:5432/farrlind")
    args = parse_args()
    return process_queue(args.session, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
