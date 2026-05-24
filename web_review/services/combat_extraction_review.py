import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from raglib.combat_encounter_extractor import output_path
from web_review.services import canon


class CombatExtractionReviewError(RuntimeError):
    pass


DECISION_CREATE = "create"
DECISION_REJECT = "reject"


def available_sessions() -> list[int]:
    extracted_dir = output_path("session00").parent
    if not extracted_dir.exists():
        return []
    sessions: list[int] = []
    for path in extracted_dir.glob("session*_combat_encounters.json"):
        match = re.fullmatch(r"session(\d+)_combat_encounters\.json", path.name)
        if match:
            sessions.append(int(match.group(1)))
    return sorted(sessions)


def load_extraction(session_number: int) -> dict[str, Any]:
    path = output_path(f"session{session_number:02d}")
    if not path.exists():
        raise FileNotFoundError(f"Combat encounter extraction file not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "session_number": session_number,
        "proposed_combat_encounters": document.get("proposed_combat_encounters", []),
        "rejected_candidates": document.get("rejected_candidates", []),
        "uncertainties": document.get("uncertainties", []),
    }


def reviewed_output_path(session_number: int) -> Path:
    return output_path(f"session{session_number:02d}").with_name(f"session{session_number:02d}_combat_encounters_reviewed.json")


def location_id_by_name(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    return canon.location_id(name)


def create_candidate(default_session_number: int, candidate: dict[str, Any]) -> str:
    title = (candidate.get("title") or "").strip()
    if not title:
        raise CombatExtractionReviewError("Combat encounter candidate is missing a title.")
    session_number = candidate.get("session_number") or default_session_number
    values = {
        "session_number": session_number,
        "title": title,
        "subtype": candidate.get("subtype") or "",
        "location_id": location_id_by_name(candidate.get("location")),
        "participants": candidate.get("participants") or "",
        "outcome": candidate.get("outcome") or "unknown",
        "confidence": candidate.get("confidence") or "medium",
        "notes": candidate.get("notes") or candidate.get("evidence") or "",
    }
    enemies = []
    for enemy in candidate.get("enemies") or []:
        name = (enemy.get("name") or "").strip()
        if not name:
            continue
        enemies.append({
            "name": name,
            "enemy_type": enemy.get("enemy_type") or "",
            "quantity": enemy.get("quantity"),
            "quantity_killed": enemy.get("quantity_killed"),
            "outcome": enemy.get("outcome") or "unknown",
            "confidence": enemy.get("confidence") or candidate.get("confidence") or "medium",
            "notes": enemy.get("notes") or "",
        })
    canon.create_combat_encounter(values, enemies)
    return f"Created {title}"


def apply_review(session_number: int, form: dict[str, Any]) -> dict[str, Any]:
    extraction = load_extraction(session_number)
    applied: list[str] = []
    skipped: list[str] = []
    decisions: dict[str, Any] = {
        "session_number": session_number,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "proposed_combat_encounters": [],
    }

    for index, candidate in enumerate(extraction["proposed_combat_encounters"]):
        decision = form.get(f"encounter_decision_{index}", DECISION_REJECT)
        decisions["proposed_combat_encounters"].append({"index": index, "title": candidate.get("title"), "decision": decision})
        if decision == DECISION_CREATE:
            applied.append(create_candidate(session_number, candidate))
        else:
            skipped.append(f"Rejected {candidate.get('title')}")

    path = reviewed_output_path(session_number)
    path.write_text(json.dumps({**decisions, "applied": applied, "skipped": skipped}, indent=2) + "\n", encoding="utf-8")
    return {"applied": applied, "skipped": skipped, "reviewed_path": path}
