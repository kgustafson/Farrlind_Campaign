from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError

from web_review import db


class WorkflowReadError(RuntimeError):
    pass


def _fetch(sql: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    try:
        return db.fetch_all(sql, params)
    except SQLAlchemyError as exc:
        raise WorkflowReadError(str(exc)) from exc


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
