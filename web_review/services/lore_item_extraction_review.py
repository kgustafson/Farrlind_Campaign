import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from raglib.lore_item_extractor import output_path
from web_review.services import canon


class LoreItemExtractionReviewError(RuntimeError):
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
    for path in extracted_dir.glob("session*_lore_items.json"):
        match = re.fullmatch(r"session(\d+)_lore_items\.json", path.name)
        if match:
            sessions.append(int(match.group(1)))
    return sorted(sessions)


def load_extraction(session_number: int) -> dict[str, Any]:
    path = output_path(f"session{session_number:02d}")
    if not path.exists():
        raise FileNotFoundError(f"Lore item extraction file not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "session_number": session_number,
        "known_lore_mentions": document.get("known_lore_mentions", []),
        "new_lore_candidates": document.get("new_lore_candidates", []),
        "rejected_candidates": document.get("rejected_candidates", []),
        "uncertainties": document.get("uncertainties", []),
    }


def reviewed_output_path(session_number: int) -> Path:
    return output_path(f"session{session_number:02d}").with_name(f"session{session_number:02d}_lore_items_reviewed.json")


def append_note(existing: str, note: str) -> str:
    existing = (existing or "").strip()
    note = note.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}\n{note}"


def npc_id_by_name(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    normalized = name.strip().lower()
    for row in canon.npc_rows():
        if (row.get("name") or "").strip().lower() == normalized:
            return row.get("id")
    return None


def lore_note(session_number: int, item: dict[str, Any]) -> str:
    info = item.get("new_information") or item.get("description") or "Mentioned in this session."
    source_npc = item.get("source_npc") or "unknown source"
    evidence = item.get("evidence") or "No evidence recorded."
    return f"Session {session_number}: {info} Source: {source_npc}. Evidence: {evidence}"


def update_values_from_detail(detail: dict[str, Any], item: dict[str, Any], notes: str) -> dict[str, Any]:
    description = detail.get("description") or ""
    new_information = item.get("new_information") or ""
    if new_information and new_information not in description:
        description = append_note(description, new_information)
    return {
        "title": detail.get("title") or "",
        "category": item.get("category") or detail.get("category") or "",
        "description": description,
        "source_npc_id": npc_id_by_name(item.get("source_npc")) or detail.get("source_npc_id"),
        "discovered_session": detail.get("discovered_session") if detail.get("discovered_session") is not None else item.get("session_number"),
        "is_confirmed": bool(item.get("is_confirmed") if item.get("is_confirmed") is not None else detail.get("is_confirmed")),
        "notes": notes,
    }


def apply_known_update(session_number: int, item: dict[str, Any]) -> str:
    lore_item_id = int(item["lore_item_id"])
    detail = canon.lore_item_detail(lore_item_id)
    if not detail:
        raise LoreItemExtractionReviewError(f"Lore item {lore_item_id} no longer exists.")
    notes = append_note(detail.get("notes") or "", lore_note(session_number, item))
    canon.update_lore_item(lore_item_id, update_values_from_detail(detail, item, notes))
    return f"Updated {detail.get('title')}"


def create_candidate(session_number: int, candidate: dict[str, Any]) -> str:
    title = (candidate.get("proposed_title") or "").strip()
    description = (candidate.get("description") or "").strip()
    if not title:
        raise LoreItemExtractionReviewError("New lore candidate is missing a title.")
    if not description:
        raise LoreItemExtractionReviewError("New lore candidate is missing a description.")
    canon.create_lore_item({
        "title": title,
        "category": candidate.get("category") or "",
        "description": description,
        "source_npc_id": npc_id_by_name(candidate.get("source_npc")),
        "discovered_session": candidate.get("discovered_session") or session_number,
        "is_confirmed": bool(candidate.get("is_confirmed")),
        "notes": lore_note(session_number, candidate),
    })
    return f"Created {title}"


def apply_review(session_number: int, form: dict[str, Any]) -> dict[str, Any]:
    extraction = load_extraction(session_number)
    applied: list[str] = []
    skipped: list[str] = []
    decisions: dict[str, Any] = {
        "session_number": session_number,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "known_lore_mentions": [],
        "new_lore_candidates": [],
    }

    for index, item in enumerate(extraction["known_lore_mentions"]):
        decision = form.get(f"known_decision_{index}", DECISION_IGNORE)
        decisions["known_lore_mentions"].append({"index": index, "lore_item_id": item.get("lore_item_id"), "decision": decision})
        if decision == DECISION_APPEND_NOTE:
            applied.append(apply_known_update(session_number, item))
        else:
            skipped.append(f"Ignored {item.get('canonical_title')}")

    for index, candidate in enumerate(extraction["new_lore_candidates"]):
        decision = form.get(f"new_decision_{index}", DECISION_REJECT)
        decisions["new_lore_candidates"].append({"index": index, "proposed_title": candidate.get("proposed_title"), "decision": decision})
        if decision == DECISION_CREATE:
            applied.append(create_candidate(session_number, candidate))
        else:
            skipped.append(f"Rejected {candidate.get('proposed_title')}")

    path = reviewed_output_path(session_number)
    path.write_text(json.dumps({**decisions, "applied": applied, "skipped": skipped}, indent=2) + "\n", encoding="utf-8")
    return {"applied": applied, "skipped": skipped, "reviewed_path": path}
