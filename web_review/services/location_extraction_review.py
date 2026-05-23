import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from raglib.location_extractor import output_path
from web_review.services import canon


class LocationExtractionReviewError(RuntimeError):
    pass


DECISION_IGNORE = "ignore"
DECISION_APPEND_NOTE = "append_note"
DECISION_CREATE = "create"
DECISION_REJECT = "reject"


def available_sessions() -> list[int]:
    extracted_dir = output_path("session00").parent
    if not extracted_dir.exists():
        return []
    sessions: list[int] = []
    for path in extracted_dir.glob("session*_locations.json"):
        match = re.fullmatch(r"session(\d+)_locations\.json", path.name)
        if match:
            sessions.append(int(match.group(1)))
    return sorted(sessions)


def load_extraction(session_number: int) -> dict[str, Any]:
    path = output_path(f"session{session_number:02d}")
    if not path.exists():
        raise FileNotFoundError(f"Location extraction file not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "session_number": session_number,
        "known_location_mentions": document.get("known_location_mentions", []),
        "new_location_candidates": document.get("new_location_candidates", []),
        "rejected_candidates": document.get("rejected_candidates", []),
        "uncertainties": document.get("uncertainties", []),
    }


def reviewed_output_path(session_number: int) -> Path:
    return output_path(f"session{session_number:02d}").with_name(f"session{session_number:02d}_locations_reviewed.json")


def append_note(existing: str, note: str) -> str:
    existing = (existing or "").strip()
    note = note.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}\n{note}"


def location_note(session_number: int, item: dict[str, Any]) -> str:
    info = item.get("new_information") or item.get("description") or "Mentioned in this session."
    evidence = item.get("evidence") or "No evidence recorded."
    return f"Session {session_number}: {info} Evidence: {evidence}"


def update_values_from_detail(detail: dict[str, Any], item: dict[str, Any], notes: str) -> dict[str, Any]:
    location_type_id = canon.location_type_id(item.get("location_type"))
    parent_location_id = canon.location_id(item.get("parent_location"))
    first_seen = detail.get("first_visited_session")
    return {
        "name": detail.get("name") or "",
        "location_type_id": location_type_id if location_type_id is not None else detail.get("location_type_id"),
        "parent_location_id": parent_location_id if parent_location_id is not None else detail.get("parent_location_id"),
        "description": detail.get("description") or item.get("new_information") or "",
        "is_underwater": bool(detail.get("is_underwater") or item.get("is_underwater")),
        "is_feywild": bool(detail.get("is_feywild") or item.get("is_feywild")),
        "first_visited_session": first_seen if first_seen is not None else item.get("session_number"),
        "notes": notes,
    }


def apply_known_update(session_number: int, item: dict[str, Any]) -> str:
    location_id = int(item["location_id"])
    detail = canon.location_detail(location_id)
    if not detail:
        raise LocationExtractionReviewError(f"Location {location_id} no longer exists.")
    notes = append_note(detail.get("notes") or "", location_note(session_number, item))
    canon.update_location(location_id, update_values_from_detail(detail, item, notes))
    return f"Updated {detail.get('name')}"


def create_candidate(session_number: int, candidate: dict[str, Any]) -> str:
    name = (candidate.get("proposed_name") or "").strip()
    if not name:
        raise LocationExtractionReviewError("New location candidate is missing a name.")
    canon.create_location({
        "name": name,
        "location_type_id": canon.location_type_id(candidate.get("location_type")),
        "parent_location_id": canon.location_id(candidate.get("parent_location")),
        "description": candidate.get("description") or "",
        "is_underwater": bool(candidate.get("is_underwater")),
        "is_feywild": bool(candidate.get("is_feywild")),
        "first_visited_session": candidate.get("first_visited_session") or session_number,
        "notes": location_note(session_number, candidate),
    })
    return f"Created {name}"


def apply_review(session_number: int, form: dict[str, Any]) -> dict[str, Any]:
    extraction = load_extraction(session_number)
    applied: list[str] = []
    skipped: list[str] = []
    decisions: dict[str, Any] = {
        "session_number": session_number,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "known_location_mentions": [],
        "new_location_candidates": [],
    }

    for index, item in enumerate(extraction["known_location_mentions"]):
        decision = form.get(f"known_decision_{index}", DECISION_IGNORE)
        decisions["known_location_mentions"].append({"index": index, "location_id": item.get("location_id"), "decision": decision})
        if decision == DECISION_APPEND_NOTE:
            applied.append(apply_known_update(session_number, item))
        else:
            skipped.append(f"Ignored {item.get('canonical_name')}")

    for index, candidate in enumerate(extraction["new_location_candidates"]):
        decision = form.get(f"new_decision_{index}", DECISION_REJECT)
        decisions["new_location_candidates"].append({"index": index, "proposed_name": candidate.get("proposed_name"), "decision": decision})
        if decision == DECISION_CREATE:
            applied.append(create_candidate(session_number, candidate))
        else:
            skipped.append(f"Rejected {candidate.get('proposed_name')}")

    path = reviewed_output_path(session_number)
    path.write_text(json.dumps({**decisions, "applied": applied, "skipped": skipped}, indent=2) + "\n", encoding="utf-8")
    return {"applied": applied, "skipped": skipped, "reviewed_path": path}
