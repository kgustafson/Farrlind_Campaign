import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from raglib import workflow_state
from web_review import db
from web_review.services import reviews


class WorkflowReadError(RuntimeError):
    pass


class WorkflowWriteError(RuntimeError):
    pass


def _fetch(sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    try:
        return db.fetch_all(sql, params)
    except SQLAlchemyError as exc:
        raise WorkflowReadError(str(exc)) from exc


def _execute_transaction(statements: list[tuple[str, dict[str, Any]]]) -> None:
    try:
        engine = db.make_engine()
        with engine.begin() as connection:
            for sql, params in statements:
                connection.execute(text(sql), params)
    except SQLAlchemyError as exc:
        raise WorkflowWriteError(str(exc)) from exc


def _split_sql(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def next_session_number() -> int:
    rows = _fetch("SELECT COALESCE(MAX(session_number), -1) + 1 AS next_session_number FROM session;")
    return int(rows[0]["next_session_number"]) if rows else 0


def initiate_session(values: dict[str, Any]) -> int:
    try:
        session_number = workflow_state.parse_session_number(values["session_number"])
    except (KeyError, ValueError) as exc:
        raise WorkflowWriteError(str(exc)) from exc

    title = (values.get("title") or f"Session {session_number:02d}").strip()
    session_date = (values.get("session_date") or "").strip() or None
    audio_path = (values.get("audio_file_path") or "").strip()
    notes = (values.get("notes") or "").strip()
    definition = workflow_state.load_workflow_definition()

    metadata = {
        "initiated_from": "project_utilities",
        "real_session_date": session_date,
        "audio_file_path": audio_path or None,
    }
    if audio_path:
        metadata["audio_file_exists_at_initiation"] = Path(audio_path).expanduser().exists()

    summary_comment = "Session workflow initiated from Project Utilities."
    if audio_path:
        summary_comment += f" Audio path registered: {audio_path}."
    if notes:
        summary_comment += f" {notes}"

    statements: list[tuple[str, dict[str, Any]]] = []
    statements.extend((statement, {}) for statement in _split_sql(workflow_state.workflow_state_schema_sql()))
    statements.extend((statement, {}) for statement in _split_sql(workflow_state.workflow_init_body_sql(session_number, definition)))
    statements.append((
        """
        UPDATE session
        SET
            session_date = COALESCE(CAST(:session_date AS date), session_date),
            title = :title,
            audio_file_path = COALESCE(NULLIF(:audio_file_path, ''), audio_file_path),
            notes = CASE
                WHEN NULLIF(:notes, '') IS NULL THEN notes
                WHEN notes IS NULL OR notes = '' THEN :notes
                ELSE notes || E'\n' || :notes
            END
        WHERE session_number = :session_number;
        """,
        {
            "session_number": session_number,
            "session_date": session_date,
            "title": title,
            "audio_file_path": audio_path,
            "notes": notes,
        },
    ))
    statements.append((
        """
        UPDATE workflow_run wr
        SET
            summary_comment = :summary_comment,
            metadata = wr.metadata || CAST(:metadata AS jsonb)
        FROM session s
        WHERE wr.session_id = s.id
          AND s.session_number = :session_number
          AND wr.workflow_id = :workflow_id
          AND wr.workflow_version = :workflow_version;
        """,
        {
            "session_number": session_number,
            "workflow_id": definition["workflow"]["id"],
            "workflow_version": int(definition["workflow"]["version"]),
            "summary_comment": summary_comment,
            "metadata": json.dumps(metadata),
        },
    ))

    if audio_path:
        audio_exists = Path(audio_path).expanduser().exists()
        statements.append((
            """
            UPDATE workflow_step_state wss
            SET
                status = :status,
                started_at = COALESCE(started_at, CASE WHEN :status = 'complete' THEN NOW() ELSE started_at END),
                completed_at = CASE WHEN :status = 'complete' THEN COALESCE(completed_at, NOW()) ELSE completed_at END,
                summary_comment = :summary_comment,
                inputs = CAST(:artifacts AS jsonb),
                outputs = CAST(:artifacts AS jsonb),
                metadata = wss.metadata || CAST(:metadata AS jsonb)
            FROM workflow_run wr
            JOIN session s ON s.id = wr.session_id
            WHERE wss.workflow_run_id = wr.id
              AND s.session_number = :session_number
              AND wr.workflow_id = :workflow_id
              AND wr.workflow_version = :workflow_version
              AND wss.step_id = 'source_audio_registered';
            """,
            {
                "session_number": session_number,
                "workflow_id": definition["workflow"]["id"],
                "workflow_version": int(definition["workflow"]["version"]),
                "status": "complete" if audio_exists else "pending",
                "summary_comment": f"Audio path registered: {audio_path} ({'file exists' if audio_exists else 'file not found yet'}).",
                "artifacts": json.dumps([audio_path]),
                "metadata": json.dumps({"audio_file_path": audio_path, "audio_file_exists": audio_exists}),
            },
        ))

    _execute_transaction(statements)
    return session_number


def workflow_rows() -> list[dict[str, Any]]:
    rows = _fetch("""
        SELECT
            s.session_number,
            COALESCE(s.title, 'Session ' || LPAD(s.session_number::text, 2, '0')) AS session_title,
            wr.workflow_id,
            wr.workflow_version,
            wr.status,
            wr.started_at,
            wr.completed_at,
            wr.summary_comment,
            COUNT(wss.id) AS total_steps,
            COUNT(wss.id) FILTER (WHERE wss.status = 'complete') AS complete_steps,
            COUNT(wss.id) FILTER (WHERE wss.status = 'not_applicable') AS not_applicable_steps,
            COUNT(wss.id) FILTER (WHERE wss.status = 'pending') AS pending_steps,
            COUNT(wss.id) FILTER (WHERE wss.status = 'blocked') AS blocked_steps,
            COUNT(wss.id) FILTER (WHERE wss.status = 'stale') AS stale_steps,
            COUNT(wss.id) FILTER (WHERE wss.status IN ('pending', 'blocked', 'stale')) AS attention_count,
            ROUND(
                100.0 * COUNT(wss.id) FILTER (WHERE wss.status IN ('complete', 'not_applicable'))
                / NULLIF(COUNT(wss.id), 0),
                0
            )::int AS progress_percent,
            next_step.display_name AS next_step_name,
            next_step.status AS next_step_status
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        LEFT JOIN workflow_step_state wss ON wss.workflow_run_id = wr.id
        LEFT JOIN LATERAL (
            SELECT display_name, status
            FROM workflow_step_state
            WHERE workflow_run_id = wr.id
              AND status NOT IN ('complete', 'not_applicable')
            ORDER BY step_order
            LIMIT 1
        ) next_step ON TRUE
        GROUP BY
            s.session_number, s.title, wr.workflow_id, wr.workflow_version, wr.status,
            wr.started_at, wr.completed_at, wr.summary_comment,
            next_step.display_name, next_step.status
        ORDER BY s.session_number DESC;
    """)
    for row in rows:
        row["session_key"] = session_key(row["session_number"])
        row["workflow_url"] = f"/workflow?session={row['session_number']}"
        row["has_attention"] = bool(row.get("attention_count"))
    return rows


def workflow_detail(session_number: int) -> Optional[dict[str, Any]]:
    runs = _fetch("""
        SELECT
            s.session_number,
            COALESCE(s.title, 'Session ' || LPAD(s.session_number::text, 2, '0')) AS session_title,
            wr.id,
            wr.workflow_id,
            wr.workflow_version,
            wr.workflow_name,
            wr.status,
            wr.initiated_at,
            wr.started_at,
            wr.completed_at,
            wr.summary_comment,
            wr.metadata
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE s.session_number = :session_number
        ORDER BY wr.workflow_version DESC, wr.id DESC
        LIMIT 1;
    """, {"session_number": session_number})
    if not runs:
        return None

    run = runs[0]
    run["session_key"] = session_key(run["session_number"])
    run["review_url"] = f"/sessions/{run['session_key']}/review"
    run["workflow_url"] = f"/workflow?session={run['session_number']}"
    run["steps"] = _fetch("""
        SELECT
            step_order,
            step_id,
            display_name,
            lane,
            status,
            started_at,
            completed_at,
            summary_comment,
            inputs,
            outputs,
            dependencies,
            gate,
            rerun_policy,
            canon_impact,
            command,
            status_rules,
            metadata
        FROM workflow_step_state
        WHERE workflow_run_id = :workflow_run_id
        ORDER BY step_order;
    """, {"workflow_run_id": run["id"]})
    for step in run["steps"]:
        step["links"] = step_links(step["step_id"], run["session_number"])
        step["issues"] = step_issues(step)
    run["attention_items"] = [
        {"step": step["display_name"], "issues": step["issues"]}
        for step in run["steps"]
        if step["issues"]
    ]
    return run


def session_key(session_number: int) -> str:
    return f"session{session_number:02d}"


def step_links(step_id: str, session_number: int) -> list[dict[str, str]]:
    key = session_key(session_number)
    review_url = f"/sessions/{key}/review"
    links_by_step = {
        "initialize_review": [{"label": "Review", "url": review_url}],
        "edit_review_decisions": [{"label": "Review", "url": review_url}],
        "mark_reviewed": [{"label": "Review", "url": review_url}],
        "apply_review": [{"label": "Review", "url": review_url}],
        "write_final_summary": [{"label": "Final Summary", "url": f"{review_url}?source=final&view=print"}],
        "update_lore_sections": [
            {"label": "Wells", "url": "/wells"},
            {"label": "NPCs", "url": "/npcs"},
            {"label": "Locations", "url": "/locations"},
            {"label": "Artifacts", "url": "/artifacts"},
        ],
        "run_health": [{"label": "Review Tools", "url": review_url}],
        "dbload_refresh": [{"label": "Dashboard", "url": "/"}],
    }
    return links_by_step.get(step_id, [])


def step_issues(step: dict[str, Any]) -> list[str]:
    issues = status_issues(step)
    issues.extend(missing_artifact_issues("input", step.get("inputs") or []))
    issues.extend(missing_artifact_issues("output", step.get("outputs") or []))
    return issues


def status_issues(step: dict[str, Any]) -> list[str]:
    status = step.get("status")
    comment = step.get("summary_comment") or ""
    if status == "pending":
        return [comment or "Step is pending."]
    if status == "blocked":
        return [comment or "Step is blocked."]
    if status == "stale":
        return [comment or "Step may be stale."]
    return []


def missing_artifact_issues(kind: str, artifacts: list[Any]) -> list[str]:
    issues = []
    for artifact in artifacts:
        if not isinstance(artifact, str) or not is_file_artifact(artifact):
            continue
        if is_optional_artifact(artifact):
            continue
        if "*" in artifact:
            if not list(reviews.REPO_ROOT.glob(artifact)):
                issues.append(f"Missing {kind} artifact matching {artifact}.")
            continue
        if not (reviews.REPO_ROOT / artifact).exists():
            issues.append(f"Missing {kind} artifact {artifact}.")
    return issues


def is_file_artifact(value: str) -> bool:
    if value.startswith("/"):
        return False
    if value.startswith(("operator ", "database ", "reviewed ", "source artifacts", "test result", "health report", "local ", "GitHub ")):
        return False
    suffixes = (
        ".wav",
        ".txt",
        ".md",
        ".yaml",
        ".yml",
        ".sql",
        ".json",
    )
    return any(value.endswith(suffix) for suffix in suffixes) or "*" in value


def is_optional_artifact(value: str) -> bool:
    return value.startswith("knowledge/Faban/notes/") and value.endswith("_corrections.md")
