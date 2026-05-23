import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from raglib.open_thread_extractor import output_path
from web_review.services import canon


class OpenThreadExtractionReviewError(RuntimeError):
    pass


DECISION_IGNORE = "ignore"
DECISION_UPDATE = "update"
DECISION_CREATE = "create"
DECISION_REJECT = "reject"


def available_sessions() -> list[int]:
    extracted_dir = output_path("session00").parent
    if not extracted_dir.exists():
        return []
    sessions: list[int] = []
    for path in extracted_dir.glob("session*_open_threads.json"):
        match = re.fullmatch(r"session(\d+)_open_threads\.json", path.name)
        if match:
            sessions.append(int(match.group(1)))
    return sorted(sessions)


def load_extraction(session_number: int) -> dict[str, Any]:
    path = output_path(f"session{session_number:02d}")
    if not path.exists():
        raise FileNotFoundError(f"Open thread extraction file not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "session_number": session_number,
        "known_thread_mentions": document.get("known_thread_mentions", []),
        "new_thread_candidates": document.get("new_thread_candidates", []),
        "rejected_candidates": document.get("rejected_candidates", []),
        "uncertainties": document.get("uncertainties", []),
    }


def reviewed_output_path(session_number: int) -> Path:
    return output_path(f"session{session_number:02d}").with_name(f"session{session_number:02d}_open_threads_reviewed.json")


def append_note(existing: str, note: str) -> str:
    existing = (existing or "").strip()
    note = note.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}\n{note}"


def location_id_by_name(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    return canon.location_id(name)


def open_thread_note(session_number: int, item: dict[str, Any]) -> str:
    info = item.get("new_information") or item.get("description") or "Mentioned in this session."
    evidence = item.get("evidence") or "No evidence recorded."
    return f"Session {session_number}: {info} Evidence: {evidence}"


def valid_status(value: Optional[str], fallback: str) -> str:
    statuses = {row["code"] for row in canon.open_thread_statuses()}
    value = (value or "").strip()
    return value if value in statuses else fallback


def valid_thread_type(value: Optional[str], fallback: str) -> str:
    thread_types = set(canon.open_thread_types())
    value = (value or "").strip()
    return value if value in thread_types else fallback


def update_values_from_detail(detail: dict[str, Any], item: dict[str, Any], notes: str, session_number: int) -> dict[str, Any]:
    description = detail.get("description") or ""
    new_information = item.get("new_information") or ""
    if new_information and new_information not in description:
        description = append_note(description, new_information)
    return {
        "title": detail.get("title") or "",
        "thread_type": valid_thread_type(item.get("thread_type"), detail.get("thread_type") or "lore_mystery"),
        "status": valid_status(item.get("status"), detail.get("status") or "open"),
        "first_session": detail.get("first_session") if detail.get("first_session") is not None else item.get("first_session") or session_number,
        "last_session": item.get("last_session") or detail.get("last_session") or session_number,
        "related_location_id": location_id_by_name(item.get("related_location")) or detail.get("related_location_id"),
        "description": description,
        "resolution": item.get("resolution") or detail.get("resolution") or "",
        "notes": notes,
    }


def apply_known_update(session_number: int, item: dict[str, Any]) -> str:
    thread_id = int(item["thread_id"])
    detail = canon.open_thread_detail(thread_id)
    if not detail:
        raise OpenThreadExtractionReviewError(f"Open thread {thread_id} no longer exists.")
    notes = append_note(detail.get("notes") or "", open_thread_note(session_number, item))
    canon.update_open_thread(thread_id, update_values_from_detail(detail, item, notes, session_number))
    return f"Updated {detail.get('title')}"


def create_candidate(session_number: int, candidate: dict[str, Any]) -> str:
    title = (candidate.get("proposed_title") or "").strip()
    description = (candidate.get("description") or "").strip()
    if not title:
        raise OpenThreadExtractionReviewError("New open thread candidate is missing a title.")
    if not description:
        raise OpenThreadExtractionReviewError("New open thread candidate is missing a description.")
    canon.create_open_thread({
        "title": title,
        "thread_type": valid_thread_type(candidate.get("thread_type"), "lore_mystery"),
        "status": valid_status(candidate.get("status"), "open"),
        "first_session": candidate.get("first_session") or session_number,
        "last_session": candidate.get("last_session") or session_number,
        "related_location_id": location_id_by_name(candidate.get("related_location")),
        "description": description,
        "resolution": candidate.get("resolution") or "",
        "notes": open_thread_note(session_number, candidate),
    })
    return f"Created {title}"


def apply_review(session_number: int, form: dict[str, Any]) -> dict[str, Any]:
    extraction = load_extraction(session_number)
    applied: list[str] = []
    skipped: list[str] = []
    decisions: dict[str, Any] = {
        "session_number": session_number,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "known_thread_mentions": [],
        "new_thread_candidates": [],
    }

    for index, item in enumerate(extraction["known_thread_mentions"]):
        decision = form.get(f"known_decision_{index}", DECISION_IGNORE)
        decisions["known_thread_mentions"].append({"index": index, "thread_id": item.get("thread_id"), "decision": decision})
        if decision == DECISION_UPDATE:
            applied.append(apply_known_update(session_number, item))
        else:
            skipped.append(f"Ignored {item.get('canonical_title')}")

    for index, candidate in enumerate(extraction["new_thread_candidates"]):
        decision = form.get(f"new_decision_{index}", DECISION_REJECT)
        decisions["new_thread_candidates"].append({"index": index, "proposed_title": candidate.get("proposed_title"), "decision": decision})
        if decision == DECISION_CREATE:
            applied.append(create_candidate(session_number, candidate))
        else:
            skipped.append(f"Rejected {candidate.get('proposed_title')}")

    path = reviewed_output_path(session_number)
    path.write_text(json.dumps({**decisions, "applied": applied, "skipped": skipped}, indent=2) + "\n", encoding="utf-8")
    return {"applied": applied, "skipped": skipped, "reviewed_path": path}
