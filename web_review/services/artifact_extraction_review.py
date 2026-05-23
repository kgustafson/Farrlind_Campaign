import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from raglib.artifact_extractor import output_path
from web_review.services import canon


class ArtifactExtractionReviewError(RuntimeError):
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
    for path in extracted_dir.glob("session*_artifacts.json"):
        match = re.fullmatch(r"session(\d+)_artifacts\.json", path.name)
        if match:
            sessions.append(int(match.group(1)))
    return sorted(sessions)


def load_extraction(session_number: int) -> dict[str, Any]:
    path = output_path(f"session{session_number:02d}")
    if not path.exists():
        raise FileNotFoundError(f"Artifact extraction file not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "session_number": session_number,
        "known_artifact_mentions": document.get("known_artifact_mentions", []),
        "new_artifact_candidates": document.get("new_artifact_candidates", []),
        "rejected_candidates": document.get("rejected_candidates", []),
        "uncertainties": document.get("uncertainties", []),
    }


def reviewed_output_path(session_number: int) -> Path:
    return output_path(f"session{session_number:02d}").with_name(f"session{session_number:02d}_artifacts_reviewed.json")


def append_note(existing: str, note: str) -> str:
    existing = (existing or "").strip()
    note = note.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}\n{note}"


def artifact_note(session_number: int, item: dict[str, Any]) -> str:
    info = item.get("new_information") or item.get("description") or "Mentioned in this session."
    holder = item.get("current_holder") or "unknown holder"
    properties = item.get("properties") or []
    property_text = f" Properties: {', '.join(properties)}." if properties else ""
    evidence = item.get("evidence") or "No evidence recorded."
    return f"Session {session_number}: {info} Holder: {holder}.{property_text} Evidence: {evidence}"


def update_values_from_detail(detail: dict[str, Any], item: dict[str, Any], notes: str) -> dict[str, Any]:
    artifact_type_id = canon.artifact_type_id(item.get("artifact_type"))
    lore_significance = detail.get("lore_significance") or item.get("new_information") or ""
    return {
        "name": detail.get("name") or "",
        "artifact_type_id": artifact_type_id if artifact_type_id is not None else detail.get("artifact_type_id"),
        "discovered_session": detail.get("discovered_session") if detail.get("discovered_session") is not None else item.get("session_number"),
        "description": detail.get("description") or item.get("new_information") or "",
        "lore_significance": lore_significance,
        "is_sentient": bool(detail.get("is_sentient") or item.get("is_sentient")),
        "is_cursed": bool(detail.get("is_cursed") or item.get("is_cursed")),
        "is_infernal": bool(detail.get("is_infernal") or item.get("is_infernal")),
        "notes": notes,
    }


def apply_known_update(session_number: int, item: dict[str, Any]) -> str:
    artifact_id = int(item["artifact_id"])
    detail = canon.artifact_detail(artifact_id)
    if not detail:
        raise ArtifactExtractionReviewError(f"Artifact {artifact_id} no longer exists.")
    notes = append_note(detail.get("notes") or "", artifact_note(session_number, item))
    canon.update_artifact(artifact_id, update_values_from_detail(detail, item, notes))
    return f"Updated {detail.get('name')}"


def create_candidate(session_number: int, candidate: dict[str, Any]) -> str:
    name = (candidate.get("proposed_name") or "").strip()
    if not name:
        raise ArtifactExtractionReviewError("New artifact candidate is missing a name.")
    canon.create_artifact({
        "name": name,
        "artifact_type_id": canon.artifact_type_id(candidate.get("artifact_type")),
        "discovered_session": candidate.get("discovered_session") or session_number,
        "description": candidate.get("description") or "",
        "lore_significance": candidate.get("lore_significance") or "",
        "is_sentient": bool(candidate.get("is_sentient")),
        "is_cursed": bool(candidate.get("is_cursed")),
        "is_infernal": bool(candidate.get("is_infernal")),
        "notes": artifact_note(session_number, candidate),
    })
    return f"Created {name}"


def apply_review(session_number: int, form: dict[str, Any]) -> dict[str, Any]:
    extraction = load_extraction(session_number)
    applied: list[str] = []
    skipped: list[str] = []
    decisions: dict[str, Any] = {
        "session_number": session_number,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "known_artifact_mentions": [],
        "new_artifact_candidates": [],
    }

    for index, item in enumerate(extraction["known_artifact_mentions"]):
        decision = form.get(f"known_decision_{index}", DECISION_IGNORE)
        decisions["known_artifact_mentions"].append({"index": index, "artifact_id": item.get("artifact_id"), "decision": decision})
        if decision == DECISION_APPEND_NOTE:
            applied.append(apply_known_update(session_number, item))
        else:
            skipped.append(f"Ignored {item.get('canonical_name')}")

    for index, candidate in enumerate(extraction["new_artifact_candidates"]):
        decision = form.get(f"new_decision_{index}", DECISION_REJECT)
        decisions["new_artifact_candidates"].append({"index": index, "proposed_name": candidate.get("proposed_name"), "decision": decision})
        if decision == DECISION_CREATE:
            applied.append(create_candidate(session_number, candidate))
        else:
            skipped.append(f"Rejected {candidate.get('proposed_name')}")

    path = reviewed_output_path(session_number)
    path.write_text(json.dumps({**decisions, "applied": applied, "skipped": skipped}, indent=2) + "\n", encoding="utf-8")
    return {"applied": applied, "skipped": skipped, "reviewed_path": path}
