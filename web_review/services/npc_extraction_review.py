import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from raglib.npc_extractor import output_path
from web_review.services import canon


class NpcExtractionReviewError(RuntimeError):
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
    for path in extracted_dir.glob("session*_npcs.json"):
        match = re.fullmatch(r"session(\d+)_npcs\.json", path.name)
        if match:
            sessions.append(int(match.group(1)))
    return sorted(sessions)


def load_extraction(session_number: int) -> dict[str, Any]:
    path = output_path(f"session{session_number:02d}")
    if not path.exists():
        raise FileNotFoundError(f"NPC extraction file not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "session_number": session_number,
        "known_npc_mentions": document.get("known_npc_mentions", []),
        "new_npc_candidates": document.get("new_npc_candidates", []),
        "rejected_candidates": document.get("rejected_candidates", []),
        "uncertainties": document.get("uncertainties", []),
    }


def reviewed_output_path(session_number: int) -> Path:
    return output_path(f"session{session_number:02d}").with_name(f"session{session_number:02d}_npcs_reviewed.json")


def append_note(existing: str, note: str) -> str:
    existing = (existing or "").strip()
    note = note.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}\n{note}"


def known_note(session_number: int, item: dict[str, Any]) -> str:
    info = item.get("new_information") or "Mentioned in this session."
    location = item.get("location") or "unknown location"
    evidence = item.get("evidence") or "No evidence recorded."
    return f"Session {session_number}: {info} Location: {location}. Evidence: {evidence}"


def values_from_detail(detail: dict[str, Any], notes: str, location_id: Optional[int]) -> dict[str, Any]:
    return {
        "name": detail.get("name") or "",
        "alias": detail.get("alias") or "",
        "faction_id": detail.get("faction_id"),
        "entity_status_id": detail.get("entity_status_id"),
        "last_known_location_id": location_id if location_id is not None else detail.get("last_known_location_id"),
        "first_seen_session": detail.get("first_seen_session"),
        "description": detail.get("description") or "",
        "is_named": bool(detail.get("is_named")),
        "notes": notes,
    }


def apply_known_update(session_number: int, item: dict[str, Any]) -> str:
    npc_id = int(item["npc_id"])
    detail = canon.npc_detail(npc_id)
    if not detail:
        raise NpcExtractionReviewError(f"NPC {npc_id} no longer exists.")
    location_id = canon.location_id(item.get("location"))
    notes = append_note(detail.get("notes") or "", known_note(session_number, item))
    canon.update_npc(npc_id, values_from_detail(detail, notes, location_id))
    return f"Updated {detail.get('name')}"


def create_candidate(session_number: int, candidate: dict[str, Any]) -> str:
    name = (candidate.get("proposed_name") or "").strip()
    if not name:
        raise NpcExtractionReviewError("New NPC candidate is missing a name.")
    location_id = canon.location_id(candidate.get("first_seen_location"))
    status_id = canon.entity_status_id(candidate.get("status") or "unknown")
    description_parts = [candidate.get("description") or "", candidate.get("role") or ""]
    description = " ".join(part.strip() for part in description_parts if part and part.strip()).strip()
    notes = known_note(session_number, {
        "new_information": candidate.get("description") or candidate.get("role") or "Created from NPC extraction.",
        "location": candidate.get("first_seen_location") or "",
        "evidence": candidate.get("evidence") or "",
    })
    aliases = candidate.get("aliases") or []
    canon.create_npc({
        "name": name,
        "alias": ", ".join(str(alias) for alias in aliases if alias),
        "faction_id": None,
        "entity_status_id": status_id,
        "last_known_location_id": location_id,
        "first_seen_session": candidate.get("first_seen_session") or session_number,
        "description": description,
        "is_named": candidate.get("npc_kind") != "group",
        "notes": notes,
    })
    return f"Created {name}"


def apply_review(session_number: int, form: dict[str, Any]) -> dict[str, Any]:
    extraction = load_extraction(session_number)
    applied: list[str] = []
    skipped: list[str] = []
    decisions: dict[str, Any] = {
        "session_number": session_number,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "known_npc_mentions": [],
        "new_npc_candidates": [],
    }

    for index, item in enumerate(extraction["known_npc_mentions"]):
        decision = form.get(f"known_decision_{index}", DECISION_IGNORE)
        decisions["known_npc_mentions"].append({"index": index, "npc_id": item.get("npc_id"), "decision": decision})
        if decision == DECISION_APPEND_NOTE:
            applied.append(apply_known_update(session_number, item))
        else:
            skipped.append(f"Ignored {item.get('canonical_name')}")

    for index, candidate in enumerate(extraction["new_npc_candidates"]):
        decision = form.get(f"new_decision_{index}", DECISION_REJECT)
        decisions["new_npc_candidates"].append({"index": index, "proposed_name": candidate.get("proposed_name"), "decision": decision})
        if decision == DECISION_CREATE:
            applied.append(create_candidate(session_number, candidate))
        else:
            skipped.append(f"Rejected {candidate.get('proposed_name')}")

    path = reviewed_output_path(session_number)
    path.write_text(json.dumps({**decisions, "applied": applied, "skipped": skipped}, indent=2) + "\n", encoding="utf-8")
    return {"applied": applied, "skipped": skipped, "reviewed_path": path}
