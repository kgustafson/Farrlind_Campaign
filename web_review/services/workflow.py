import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from raglib import workflow_state
from raglib import campaign
from raglib.audio import is_supported_audio_path, resolve_session_audio_path
from web_review import db
from web_review.services import reviews


QUEUE_DIR = reviews.REPO_ROOT / "ops" / "workflow_queue"
TRANSCRIPT_POLICIES = {"use_existing", "recreate"}
TERMINAL_STEP_STATUSES = {"complete", "not_applicable"}
SESSION_INGEST_LANES = {"intake", "draft_generation", "entity_extraction", "human_review", "canonization"}
DRAFT_RERUN_COMMANDS = [
    "source_status_check",
    "curate_transcript",
    "generate_narrative_summary",
    "extract_session_spine",
    "validate_session_spine",
    "extract_npcs",
    "extract_locations",
    "extract_artifacts",
    "extract_lore_items",
    "extract_combat_encounters",
    "extract_open_threads",
    "extract_events",
    "postextract_shortcut",
]


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
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    index = 0
    while index < len(sql):
        char = sql[index]
        current.append(char)
        if char == "'":
            if in_single_quote and index + 1 < len(sql) and sql[index + 1] == "'":
                current.append(sql[index + 1])
                index += 1
            else:
                in_single_quote = not in_single_quote
        elif char == ";" and not in_single_quote:
            statement = "".join(current[:-1]).strip()
            if statement:
                statements.append(statement)
            current = []
        index += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def next_session_number() -> int:
    rows = _fetch("SELECT COALESCE(MAX(session_number), -1) + 1 AS next_session_number FROM session;")
    return int(rows[0]["next_session_number"]) if rows else 0


def artifact_candidates(value: str) -> list[Path]:
    raw = (value or "").strip()
    if not raw:
        return []
    path = Path(raw).expanduser()
    candidates = [path]
    if not path.is_absolute():
        candidates.append(reviews.REPO_ROOT / path)

    marker = "/campaigns/"
    if marker in raw:
        tail = raw.split(marker, 1)[1]
        candidates.append(reviews.REPO_ROOT / "campaigns" / tail)

    unique: list[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def artifact_exists(value: str) -> bool:
    return any(path.exists() for path in artifact_candidates(value))


def storage_artifact_path(value: str) -> str:
    raw = (value or "").strip()
    for candidate in artifact_candidates(raw):
        try:
            return candidate.resolve().relative_to(reviews.REPO_ROOT.resolve()).as_posix()
        except (FileNotFoundError, ValueError):
            try:
                return candidate.absolute().relative_to(reviews.REPO_ROOT.absolute()).as_posix()
            except ValueError:
                continue

    marker = "/campaigns/"
    if marker in raw:
        return f"campaigns/{raw.split(marker, 1)[1]}"
    return raw


def repo_artifact(path: Path) -> str:
    try:
        return path.relative_to(reviews.REPO_ROOT).as_posix()
    except ValueError:
        return storage_artifact_path(str(path))


def discovered_audio_artifact(session_name: str) -> str:
    path = resolve_session_audio_path(session_name)
    return repo_artifact(path) if path.exists() else ""


def registered_audio_artifact(original_audio_path: str, session_name: str) -> str:
    if original_audio_path:
        if not is_supported_audio_path(original_audio_path):
            raise WorkflowWriteError("Audio file must use a supported extension: .wav, .mp3, .m4a, .flac, .aac, or .ogg.")
        return storage_artifact_path(original_audio_path)
    return discovered_audio_artifact(session_name)


def normalize_transcript_policy(value: Optional[str]) -> str:
    policy = (value or "").strip()
    return policy if policy in TRANSCRIPT_POLICIES else "use_existing"


def initiate_session(values: dict[str, Any]) -> int:
    try:
        session_number = workflow_state.parse_session_number(values["session_number"])
    except (KeyError, ValueError) as exc:
        raise WorkflowWriteError(str(exc)) from exc

    title = (values.get("title") or f"Session {session_number:02d}").strip()
    session_date = (values.get("session_date") or "").strip() or None
    transcript_policy = normalize_transcript_policy(values.get("transcript_policy"))
    notes = (values.get("notes") or "").strip()
    definition = workflow_state.load_workflow_definition()
    session_name = workflow_state.session_name(session_number)
    original_audio_path = (values.get("audio_file_path") or "").strip()
    audio_path = registered_audio_artifact(original_audio_path, session_name)
    transcript_artifact = repo_artifact(campaign.raw_dir() / f"{session_name}_transcript.txt")
    diary_artifact = repo_artifact(campaign.clean_dir() / f"{session_name}_diary.md")

    metadata = {
        "initiated_from": "project_utilities",
        "real_session_date": session_date,
        "audio_file_path": audio_path or None,
        "audio_extension": Path(audio_path).suffix.lower() if audio_path else None,
        "audio_stem": Path(audio_path).stem if audio_path else None,
        "transcript_policy": transcript_policy,
    }
    if original_audio_path and original_audio_path != audio_path:
        metadata["original_audio_file_path"] = original_audio_path
    if audio_path:
        metadata["audio_file_exists_at_initiation"] = artifact_exists(audio_path)

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
        audio_exists = artifact_exists(audio_path)
        statements.append((
            """
            UPDATE workflow_step_state wss
            SET
                status = :status,
                started_at = COALESCE(wss.started_at, CASE WHEN :status = 'complete' THEN NOW() ELSE wss.started_at END),
                completed_at = CASE WHEN :status = 'complete' THEN COALESCE(wss.completed_at, NOW()) ELSE wss.completed_at END,
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
        statements.append((
            """
            UPDATE workflow_step_state wss
            SET
                inputs = CAST(:inputs AS jsonb),
                outputs = CAST(:outputs AS jsonb),
                summary_comment = CASE
                    WHEN wss.status = 'pending' THEN :summary_comment
                    ELSE wss.summary_comment
                END,
                metadata = wss.metadata || CAST(:metadata AS jsonb)
            FROM workflow_run wr
            JOIN session s ON s.id = wr.session_id
            WHERE wss.workflow_run_id = wr.id
              AND s.session_number = :session_number
              AND wr.workflow_id = :workflow_id
              AND wr.workflow_version = :workflow_version
              AND wss.step_id = 'transcribe_audio';
            """,
            {
                "session_number": session_number,
                "workflow_id": definition["workflow"]["id"],
                "workflow_version": int(definition["workflow"]["version"]),
                "inputs": json.dumps([audio_path]),
                "outputs": json.dumps([transcript_artifact]),
                "summary_comment": (
                    "Auto-intake will use an existing raw transcript if present."
                    if transcript_policy == "use_existing"
                    else "Auto-intake will recreate the raw transcript from registered source audio."
                ),
                "metadata": json.dumps({
                    "audio_file_path": audio_path,
                    "audio_file_exists": audio_exists,
                    "transcript_policy": transcript_policy,
                }),
            },
        ))
        statements.append((
            """
            UPDATE workflow_step_state wss
            SET inputs = CAST(:inputs AS jsonb)
            FROM workflow_run wr
            JOIN session s ON s.id = wr.session_id
            WHERE wss.workflow_run_id = wr.id
              AND s.session_number = :session_number
              AND wr.workflow_id = :workflow_id
              AND wr.workflow_version = :workflow_version
              AND wss.step_id = 'source_status_check';
            """,
            {
                "session_number": session_number,
                "workflow_id": definition["workflow"]["id"],
                "workflow_version": int(definition["workflow"]["version"]),
                "inputs": json.dumps([audio_path, transcript_artifact, diary_artifact]),
            },
        ))

    _execute_transaction(statements)
    return session_number


def auto_intake_enabled() -> bool:
    return True


def enqueue_auto_intake(session_number: int, transcript_policy: str = "use_existing") -> Optional[Path]:
    rows = _fetch("""
        SELECT audio_file_path
        FROM session
        WHERE session_number = :session_number;
    """, {"session_number": session_number})
    if not rows:
        raise WorkflowWriteError(f"Session {session_number:02d} does not exist.")

    audio_path = (rows[0].get("audio_file_path") or "").strip()
    if not audio_path:
        return None

    resolved_audio = Path(audio_path)
    if not resolved_audio.is_absolute():
        resolved_audio = reviews.REPO_ROOT / resolved_audio
    if not resolved_audio.exists():
        return None

    transcript_policy = normalize_transcript_policy(transcript_policy)
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "campaign_name": campaign.active_campaign_name(),
        "session_number": session_number,
        "session_name": session_key(session_number),
        "audio_file_path": audio_path,
        "transcript_policy": transcript_policy,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "stop_before": "review_npc_extraction",
        "commands": [
            "transcribe_audio",
            "source_status_check",
            "curate_transcript",
            "generate_narrative_summary",
            "extract_session_spine",
            "validate_session_spine",
            "extract_npcs",
            "extract_locations",
            "extract_artifacts",
            "extract_lore_items",
            "extract_combat_encounters",
            "extract_open_threads",
            "extract_events",
            "postextract_shortcut",
        ],
    }
    queue_path = QUEUE_DIR / f"{session_key(session_number)}.json"
    temp_path = queue_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(queue_path)

    _execute_transaction([
        ("""
        UPDATE workflow_run wr
        SET
            status = CASE WHEN wr.status = 'initialized' THEN 'pending' ELSE wr.status END,
            summary_comment = COALESCE(wr.summary_comment || ' ', '') || :summary_comment,
            metadata = wr.metadata || CAST(:metadata AS jsonb)
        FROM session s
        WHERE wr.session_id = s.id
          AND s.session_number = :session_number;
        """, {
            "session_number": session_number,
            "summary_comment": "Auto-intake queued through draft extraction; extraction reviews are the next human gate.",
            "metadata": json.dumps({
                "auto_intake_queued": True,
                "auto_intake_queue_path": str(queue_path.relative_to(reviews.REPO_ROOT)),
                "transcript_policy": transcript_policy,
            }),
        }),
        ("""
        UPDATE workflow_step_state wss
        SET summary_comment = :summary_comment
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE wss.workflow_run_id = wr.id
          AND s.session_number = :session_number
          AND wss.step_id = 'transcribe_audio'
          AND wss.status = 'pending';
        """, {
            "session_number": session_number,
            "summary_comment": (
                "Queued for automatic intake; existing raw transcript will be preserved if present."
                if transcript_policy == "use_existing"
                else "Queued for automatic intake; raw transcript will be recreated from audio."
            ),
        }),
    ])
    return queue_path


def applied_entity_review_files(session_number: int) -> list[Path]:
    paths = []
    for _label, pattern in reviews.EXTRACTION_REVIEW_FILES:
        path = reviews.extraction_review_path(session_number, pattern)
        if path.exists():
            paths.append(path)
    return paths


def draft_rerun_guard(session_number: int) -> dict[str, Any]:
    session_name = session_key(session_number)
    transcript_path = campaign.raw_dir() / f"{session_name}_transcript.txt"
    applied_paths = applied_entity_review_files(session_number)
    final_summary = reviews.final_summary_path(session_number)
    reasons = []
    if not transcript_path.exists():
        reasons.append(f"Missing transcript: {repo_artifact(transcript_path)}")
    if applied_paths:
        labels = ", ".join(path.name for path in applied_paths)
        reasons.append(f"Entity reviews already applied: {labels}")
    if final_summary.exists():
        reasons.append(f"Final summary already exists: {repo_artifact(final_summary)}")
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "transcript": repo_artifact(transcript_path),
        "applied_entity_reviews": [repo_artifact(path) for path in applied_paths],
        "final_summary": repo_artifact(final_summary) if final_summary.exists() else "",
    }


def enqueue_draft_rerun(session_number: int) -> Path:
    guard = draft_rerun_guard(session_number)
    if not guard["allowed"]:
        raise WorkflowWriteError("Draft extraction rerun is blocked. " + " ".join(guard["reasons"]))

    rows = _fetch("""
        SELECT id
        FROM session
        WHERE session_number = :session_number;
    """, {"session_number": session_number})
    if not rows:
        raise WorkflowWriteError(f"Session {session_number:02d} does not exist.")

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    queue_path = QUEUE_DIR / f"{session_key(session_number)}_draft_rerun.json"
    payload = {
        "campaign_name": campaign.active_campaign_name(),
        "session_number": session_number,
        "session_name": session_key(session_number),
        "transcript_policy": "use_existing",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "job_type": "draft_rerun",
        "guard": {
            "never_overwrite_reviewed_entities": True,
            "blocked_if_reviewed_entity_files_exist": True,
            "transcript": guard["transcript"],
        },
        "commands": DRAFT_RERUN_COMMANDS,
    }
    temp_path = queue_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(queue_path)

    command_step_ids = [
        "source_status_check",
        "curate_transcript",
        "generate_narrative_summary",
        "extract_session_spine",
        "validate_session_spine",
        "extract_npcs",
        "extract_locations",
        "extract_artifacts",
        "extract_lore_items",
        "extract_combat_encounters",
        "extract_open_threads",
        "extract_events",
        "filter_events",
        "classify_events",
        "normalize_events",
        "merge_events",
        "validate_draft",
        "summarize_draft",
        "postextract_shortcut",
    ]
    review_step_ids = [
        "review_npc_extraction",
        "review_location_extraction",
        "review_artifact_extraction",
        "review_lore_item_extraction",
        "review_combat_encounter_extraction",
        "review_open_thread_extraction",
    ]
    _execute_transaction([
        ("""
        UPDATE workflow_run wr
        SET
            status = 'pending',
            completed_at = NULL,
            summary_comment = COALESCE(wr.summary_comment || ' ', '') || :summary_comment,
            metadata = wr.metadata || CAST(:metadata AS jsonb)
        FROM session s
        WHERE wr.session_id = s.id
          AND s.session_number = :session_number;
        """, {
            "session_number": session_number,
            "summary_comment": "Protected draft extraction rerun queued; reviewed entity canon will not be overwritten.",
            "metadata": json.dumps({
                "draft_rerun_queued": True,
                "draft_rerun_queue_path": str(queue_path.relative_to(reviews.REPO_ROOT)),
                "draft_rerun_guard": payload["guard"],
            }),
        }),
        ("""
        UPDATE workflow_step_state wss
        SET
            status = 'pending',
            completed_at = NULL,
            summary_comment = :summary_comment,
            metadata = wss.metadata || CAST(:metadata AS jsonb)
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE wss.workflow_run_id = wr.id
          AND s.session_number = :session_number
          AND wss.step_id = ANY(:step_ids);
        """, {
            "session_number": session_number,
            "step_ids": command_step_ids,
            "summary_comment": "Queued for protected draft extraction rerun from existing transcript.",
            "metadata": json.dumps({"draft_rerun_queued": True}),
        }),
        ("""
        UPDATE workflow_step_state wss
        SET
            status = 'pending',
            completed_at = NULL,
            summary_comment = :summary_comment,
            metadata = wss.metadata || CAST(:metadata AS jsonb)
        FROM workflow_run wr
        JOIN session s ON s.id = wr.session_id
        WHERE wss.workflow_run_id = wr.id
          AND s.session_number = :session_number
          AND wss.step_id = ANY(:step_ids);
        """, {
            "session_number": session_number,
            "step_ids": review_step_ids,
            "summary_comment": "Waiting for human review of regenerated draft entity candidates.",
            "metadata": json.dumps({"draft_rerun_queued": True}),
        }),
    ])
    return queue_path


def sync_session_workflow(session_number: int) -> None:
    definition = workflow_state.load_workflow_definition()
    sql = workflow_state.historical_workflow_seed_sql(session_number, session_number, definition)
    statements = [(statement, {}) for statement in _split_sql(sql)]
    _execute_transaction(statements)


def workflow_rows() -> list[dict[str, Any]]:
    rows = _fetch("""
        WITH latest_run AS (
            SELECT DISTINCT ON (wr.session_id)
                wr.*
            FROM workflow_run wr
            ORDER BY wr.session_id, wr.workflow_version DESC, wr.id DESC
        )
        SELECT
            s.session_number,
            COALESCE(s.title, 'Session ' || LPAD(s.session_number::text, 2, '0')) AS session_title,
            wr.workflow_id,
            wr.workflow_version,
            wr.status,
            wr.started_at,
            wr.completed_at,
            wr.summary_comment,
            COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization')) AS total_steps,
            COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization') AND wss.status = 'complete') AS complete_steps,
            COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization') AND wss.status = 'not_applicable') AS not_applicable_steps,
            COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization') AND wss.status = 'pending') AS raw_pending_steps,
            COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization') AND wss.status NOT IN ('complete', 'not_applicable')) AS pending_steps,
            COUNT(wss.id) FILTER (WHERE wss.status = 'blocked') AS blocked_steps,
            COUNT(wss.id) FILTER (WHERE wss.status = 'stale') AS stale_steps,
            COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization') AND wss.status NOT IN ('complete', 'not_applicable')) AS attention_count,
            ROUND(
                100.0 * COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization') AND wss.status IN ('complete', 'not_applicable'))
                / NULLIF(COUNT(wss.id) FILTER (WHERE wss.lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization')), 0),
                0
            )::int AS progress_percent,
            next_step.display_name AS next_step_name,
            next_step.status AS next_step_status
        FROM latest_run wr
        JOIN session s ON s.id = wr.session_id
        LEFT JOIN workflow_step_state wss ON wss.workflow_run_id = wr.id
        LEFT JOIN LATERAL (
            SELECT display_name, status
            FROM workflow_step_state
            WHERE workflow_run_id = wr.id
              AND lane IN ('intake', 'draft_generation', 'entity_extraction', 'human_review', 'canonization')
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
        total_steps = int(row.get("total_steps") or 0)
        complete_steps = int(row.get("complete_steps") or 0)
        not_applicable_steps = int(row.get("not_applicable_steps") or 0)
        if total_steps and complete_steps + not_applicable_steps == total_steps:
            row["status"] = "completed"
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
    run["draft_rerun_guard"] = draft_rerun_guard(run["session_number"])
    run["can_rerun_draft"] = bool(run["draft_rerun_guard"]["allowed"])
    run["major_status"] = major_status_items(run)
    ingest_steps = [step for step in run["steps"] if step.get("lane") in SESSION_INGEST_LANES]
    if ingest_steps and all(step.get("status") in TERMINAL_STEP_STATUSES for step in ingest_steps):
        run["status"] = "completed"
    run["attention_items"] = [
        {"step": step["display_name"], "issues": step["issues"]}
        for step in run["steps"]
        if step.get("lane") in SESSION_INGEST_LANES and step["issues"]
    ]
    return run


def major_status_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    steps = {step["step_id"]: step for step in run.get("steps") or []}
    items = [
        {
            "label": "Session Kickoff",
            "status": "complete",
            "display_status": "complete",
            "detail": run.get("summary_comment") or "Workflow row exists for this session.",
        },
        audio_validation_status(steps),
        transcription_status_item(steps),
        draft_preparation_status(steps),
    ]
    items.extend(entity_review_status_items(steps))
    items.append(final_summary_status_item(steps))
    items.append(session_complete_status_item(steps))
    return items


def audio_validation_status(steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    step = steps.get("source_audio_registered") or {}
    status = step.get("status") or "pending"
    if status == "complete":
        label = "Audio Validated"
    elif status == "not_applicable":
        label = "Audio Not Required"
    elif status == "pending":
        label = "Audio Needed"
    else:
        label = "Audio Problem"
    return {
        "label": "Audio File",
        "status": status,
        "display_status": label,
        "detail": step.get("summary_comment") or "Audio file has not been checked yet.",
    }


def transcription_status_item(steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    step = steps.get("transcribe_audio") or {}
    progress = transcription_progress(step)
    detail_parts = [step.get("summary_comment") or "Transcription has not started."]
    if progress.get("chunk_label"):
        detail_parts.append(progress["chunk_label"])
    if progress.get("elapsed_label"):
        detail_parts.append(progress["elapsed_label"])
    return {
        "label": "Transcription",
        "status": step.get("status") or "pending",
        "display_status": major_status_label(step.get("status") or "pending"),
        "detail": " ".join(part for part in detail_parts if part),
        "progress": progress,
    }


def draft_preparation_status(steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = [
        "curate_transcript",
        "generate_narrative_summary",
        "extract_session_spine",
        "validate_session_spine",
        "extract_npcs",
        "extract_locations",
        "extract_artifacts",
        "extract_lore_items",
        "extract_combat_encounters",
        "extract_open_threads",
        "extract_events",
        "postextract_shortcut",
    ]
    selected = [steps.get(step_id) for step_id in ids if steps.get(step_id)]
    status = major_status_from_steps(selected)
    complete_count = sum(1 for step in selected if step.get("status") in TERMINAL_STEP_STATUSES)
    return {
        "label": "Draft Preparation",
        "status": status,
        "display_status": major_status_label(status),
        "detail": f"{complete_count} of {len(selected)} draft/extraction steps complete.",
    }


def entity_review_status_items(steps: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [
        ("NPC Review", "review_npc_extraction"),
        ("Location Review", "review_location_extraction"),
        ("Artifact Review", "review_artifact_extraction"),
        ("Lore Review", "review_lore_item_extraction"),
        ("Combat Review", "review_combat_encounter_extraction"),
        ("Open Thread Review", "review_open_thread_extraction"),
    ]
    items = []
    for label, step_id in specs:
        step = steps.get(step_id) or {}
        status = step.get("status") or "pending"
        if status == "complete":
            display_status = "review completed"
        elif status in {"pending", "not_applicable"}:
            display_status = "needs review"
        elif status in {"blocked", "stale", "failed"}:
            display_status = "needs attention"
        else:
            display_status = major_status_label(status)
        items.append({
            "label": label,
            "status": status,
            "display_status": display_status,
            "detail": step.get("summary_comment") or "Review has not been applied yet.",
        })
    return items


def final_summary_status_item(steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ids = ["initialize_review", "edit_review_decisions", "validate_final_summary", "mark_reviewed", "apply_review", "write_final_summary"]
    selected = [steps.get(step_id) for step_id in ids if steps.get(step_id)]
    status = major_status_from_steps(selected)
    final_step = steps.get("write_final_summary") or {}
    return {
        "label": "Final Summary Review",
        "status": status,
        "display_status": "review completed" if status == "complete" else major_status_label(status),
        "detail": final_step.get("summary_comment") or "Final summary review is not complete.",
    }


def session_complete_status_item(steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    apply_step = steps.get("apply_review") or {}
    final_step = steps.get("write_final_summary") or {}
    entity_steps = [
        steps.get("review_npc_extraction") or {},
        steps.get("review_location_extraction") or {},
        steps.get("review_artifact_extraction") or {},
        steps.get("review_lore_item_extraction") or {},
        steps.get("review_combat_encounter_extraction") or {},
        steps.get("review_open_thread_extraction") or {},
    ]
    entities_complete = all(step.get("status") == "complete" for step in entity_steps)
    complete = entities_complete and apply_step.get("status") == "complete" and final_step.get("status") == "complete"
    return {
        "label": "Session Ingest",
        "status": "complete" if complete else "pending",
        "display_status": "complete" if complete else "not complete",
        "detail": "Session ingest complete." if complete else "Waiting for entity reviews and accepted final summary.",
    }


def major_status_from_steps(steps: list[Optional[dict[str, Any]]], complete_when_any_terminal: bool = False) -> str:
    real_steps = [step for step in steps if step]
    if not real_steps:
        return "pending"
    statuses = [step.get("status") or "pending" for step in real_steps]
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "running" for status in statuses):
        return "running"
    if any(status in {"blocked", "stale"} for status in statuses):
        return "blocked" if "blocked" in statuses else "stale"
    if all(status in TERMINAL_STEP_STATUSES for status in statuses):
        return "complete"
    if complete_when_any_terminal and any(status in TERMINAL_STEP_STATUSES for status in statuses):
        return "complete"
    return "pending"


def major_status_label(status: str) -> str:
    labels = {
        "complete": "complete",
        "not_applicable": "not required",
        "pending": "waiting",
        "running": "running",
        "blocked": "blocked",
        "stale": "needs attention",
        "failed": "failed",
    }
    return labels.get(status, status)


def transcription_progress(step: dict[str, Any]) -> dict[str, Any]:
    metadata = step.get("metadata") or {}
    log_path = metadata.get("log_path") if isinstance(metadata, dict) else ""
    progress: dict[str, Any] = {}
    if log_path:
        path = reviews.REPO_ROOT / log_path
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            total_match = re.search(r"\bchunks=(\d+)\b", text)
            done_chunks = len(re.findall(r"parallel done chunk-\d+", text))
            if total_match:
                total = int(total_match.group(1))
                progress["chunks_done"] = done_chunks
                progress["chunks_total"] = total
                progress["chunk_label"] = f"Chunks: {done_chunks} of {total}."
            elapsed_match = re.search(r"done parallel transcription elapsed=([\d.]+)s", text)
            if elapsed_match:
                progress["elapsed_seconds"] = float(elapsed_match.group(1))
                progress["elapsed_label"] = f"Elapsed: {format_duration(float(elapsed_match.group(1)))}."
    elapsed = elapsed_seconds(step.get("started_at"), step.get("completed_at"))
    if elapsed is not None and "elapsed_label" not in progress:
        progress["elapsed_seconds"] = elapsed
        progress["elapsed_label"] = f"Elapsed: {format_duration(elapsed)}."
    return progress


def elapsed_seconds(started_at: Any, completed_at: Any) -> Optional[float]:
    if not started_at:
        return None
    start = coerce_datetime(started_at)
    end = coerce_datetime(completed_at) if completed_at else datetime.now(timezone.utc)
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def format_duration(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def session_key(session_number: int) -> str:
    return f"session{session_number:02d}"


def step_links(step_id: str, session_number: int) -> list[dict[str, str]]:
    key = session_key(session_number)
    review_url = f"/sessions/{key}/review"
    links_by_step = {
        "review_npc_extraction": [{"label": "Review NPCs", "url": f"/npcs/extractions?session={session_number}"}],
        "review_location_extraction": [{"label": "Review Locations", "url": f"/locations/extractions?session={session_number}"}],
        "review_artifact_extraction": [{"label": "Review Artifacts", "url": f"/artifacts/extractions?session={session_number}"}],
        "review_lore_item_extraction": [{"label": "Review Lore", "url": f"/lore-items/extractions?session={session_number}"}],
        "review_combat_encounter_extraction": [{"label": "Review Combat", "url": f"/combat-encounters/extractions?session={session_number}"}],
        "review_open_thread_extraction": [{"label": "Review Threads", "url": f"/open-threads/extractions?session={session_number}"}],
        "initialize_review": [{"label": "Review", "url": review_url}],
        "edit_review_decisions": [{"label": "Review Events", "url": review_url}],
        "mark_reviewed": [{"label": "Review", "url": review_url}],
        "apply_review": [{"label": "Review", "url": review_url}],
        "write_final_summary": [{"label": "Final Summary", "url": f"{review_url}?source=final&view=print"}],
        "update_lore_sections": [
            {"label": "Lore Items", "url": "/lore-items"},
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
        ".mp3",
        ".m4a",
        ".flac",
        ".aac",
        ".ogg",
        ".txt",
        ".md",
        ".yaml",
        ".yml",
        ".sql",
        ".json",
    )
    return any(value.endswith(suffix) for suffix in suffixes) or "*" in value


def is_optional_artifact(value: str) -> bool:
    return (
        ("/notes/" in value and value.endswith("_corrections.md"))
        or value.endswith("_diary.md")
        or value.endswith("_context.yaml")
    )
