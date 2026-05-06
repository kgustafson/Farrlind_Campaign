
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import markdown
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = REPO_ROOT / "knowledge" / "Faban"
CLEAN_DIR = KNOWLEDGE_DIR / "clean"
FINAL_DIR = KNOWLEDGE_DIR / "final"
REVIEWS_DIR = KNOWLEDGE_DIR / "reviews"

VALID_DECISIONS = {"pending", "accepted", "rejected", "corrected", "added"}
VALID_STATUSES = {"in_review", "reviewed", "applied"}
EVENT_TYPES = [
    "combat",
    "discovery",
    "downtime",
    "hazard",
    "lore",
    "mystery",
    "social",
    "travel",
]


@dataclass(frozen=True)
class ReviewSummary:
    session: str
    session_number: int
    status: str
    title: str
    path: str
    review_exists: bool
    final_exists: bool
    total_items: int
    base_items: int
    added_items: int
    pending_decisions: int
    accepted: int
    rejected: int
    corrected: int
    added: int
    unknown_decisions: int
    unapplied_items: int
    next_action: str


def session_key(session_number: int) -> str:
    return f"session{session_number:02d}"


def parse_session_ref(value: Any) -> int:
    match = re.search(r"(\d+)$", str(value or "").strip())
    if not match:
        raise ValueError(f"Could not parse session reference: {value!r}")
    return int(match.group(1))


def review_path(session_number: int) -> Path:
    return REVIEWS_DIR / f"{session_key(session_number)}_review.yaml"


def diary_path(session_number: int) -> Path:
    return CLEAN_DIR / f"{session_key(session_number)}_diary.md"


def draft_summary_path(session_number: int) -> Path:
    return CLEAN_DIR / f"{session_key(session_number)}_summary.md"


def final_summary_path(session_number: int) -> Path:
    return FINAL_DIR / f"{session_key(session_number)}_summary.md"


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_review_document(session_number: int) -> dict[str, Any]:
    path = review_path(session_number)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def all_review_items(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [*(document.get("items") or []), *(document.get("added_items") or [])]


def decision_counts(document: dict[str, Any]) -> dict[str, int]:
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "corrected": 0, "added": 0, "other": 0}
    for item in all_review_items(document):
        decision = item.get("decision") or "pending"
        counts[decision if decision in counts else "other"] += 1
    return counts


def unapplied_count(document: dict[str, Any]) -> int:
    count = 0
    for item in all_review_items(document):
        if item.get("decision") in {"accepted", "rejected", "corrected", "added"}:
            if (item.get("applied_status") or "pending") != "applied":
                count += 1
    return count


def next_action_for(document: dict[str, Any]) -> str:
    if not document:
        return "init-review"
    counts = decision_counts(document)
    status = document.get("status") or "unknown"
    if counts["pending"] or counts["other"]:
        return "edit"
    if status == "in_review":
        return "mark-reviewed"
    if status in {"reviewed", "complete"} and unapplied_count(document):
        return "apply"
    if status == "applied" and not unapplied_count(document):
        return "done"
    return "inspect"


def summarize_review_document(session_number: int, document: dict[str, Any]) -> ReviewSummary:
    path = review_path(session_number)
    key = session_key(session_number)
    counts = decision_counts(document)
    items = document.get("items") or []
    added_items = document.get("added_items") or []
    return ReviewSummary(
        session=key,
        session_number=session_number,
        status=document.get("status") or ("missing" if not document else "unknown"),
        title=document.get("session_title") or "",
        path=str(path),
        review_exists=path.exists(),
        final_exists=final_summary_path(session_number).exists(),
        total_items=len(items) + len(added_items),
        base_items=len(items),
        added_items=len(added_items),
        pending_decisions=counts["pending"],
        accepted=counts["accepted"],
        rejected=counts["rejected"],
        corrected=counts["corrected"],
        added=counts["added"],
        unknown_decisions=counts["other"],
        unapplied_items=unapplied_count(document),
        next_action=next_action_for(document),
    )


def discover_session_numbers() -> list[int]:
    numbers = set()
    for directory, pattern in [
        (REVIEWS_DIR, "session*_review.yaml"),
        (CLEAN_DIR, "session*_summary.md"),
        (CLEAN_DIR, "session*_diary.md"),
        (FINAL_DIR, "session*_summary.md"),
    ]:
        if not directory.exists():
            continue
        for path in directory.glob(pattern):
            match = re.search(r"session(\d+)", path.name)
            if match:
                numbers.add(int(match.group(1)))
    return sorted(numbers)


def dashboard_rows() -> list[ReviewSummary]:
    return [
        summarize_review_document(number, load_review_document(number))
        for number in discover_session_numbers()
    ]


def sorted_review_items(document: dict[str, Any]) -> list[dict[str, Any]]:
    def sequence_value(item: dict[str, Any]) -> float:
        try:
            return float(item.get("sequence") or 0)
        except (TypeError, ValueError):
            return 0.0

    combined = []
    for section in ["items", "added_items"]:
        for item in document.get(section) or []:
            clone = dict(item)
            clone["section"] = section
            combined.append(clone)
    return sorted(combined, key=sequence_value)


def source_text(session_number: int, source: str) -> tuple[str, str]:
    choices = {
        "diary": ("Diary", diary_path(session_number)),
        "draft": ("Draft Summary", draft_summary_path(session_number)),
        "final": ("Final Summary", final_summary_path(session_number)),
    }
    label, path = choices.get(source, choices["diary"])
    text = read_text_if_exists(path)
    if not text:
        text = f"No {label.lower()} file found for {session_key(session_number)}."
    return label, text



def render_markdown(text: str) -> str:
    return markdown.markdown(
        text or "",
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )


def session_workspace(session_number: int, source: str = "diary", source_view: str = "raw") -> dict[str, Any]:
    document = load_review_document(session_number)
    label, text = source_text(session_number, source)
    return {
        "session_number": session_number,
        "session_key": session_key(session_number),
        "summary": summarize_review_document(session_number, document),
        "document": document,
        "items": sorted_review_items(document),
        "source": source,
        "source_label": label,
        "source_text": text,
        "source_html": render_markdown(text),
        "source_view": source_view if source_view in {"raw", "print"} else "raw",
        "validation": validate_review_document(document),
        "event_types": EVENT_TYPES,
        "review_locked": (document.get("status") == "applied"),
    }



def _coerce_sequence(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _coerce_significance(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _first(values: dict[str, list[str]], key: str, index: int, default: str = "") -> str:
    items = values.get(key) or []
    if index >= len(items):
        return default
    return items[index]


def next_added_item_id(document: dict[str, Any]) -> str:
    highest = 0
    for item in document.get("added_items") or []:
        match = re.search(r"added-(\d+)$", str(item.get("id") or ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"added-{highest + 1:03d}"


def build_added_item(document: dict[str, Any], values: dict[str, Any], added_on: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": next_added_item_id(document),
        "sequence": _coerce_sequence(values.get("sequence")),
        "source_type": "user_added",
        "source_text": "",
        "decision": "added",
        "canonical_text": str(values.get("canonical_text") or "").strip(),
        "event_type": str(values.get("event_type") or "").strip(),
        "location": str(values.get("location") or "").strip(),
        "significance": _coerce_significance(values.get("significance")),
        "reason": str(values.get("reason") or "").strip(),
        "decided_by": "user",
        "decided_on": added_on or date.today().isoformat(),
        "applied_status": "pending",
        "applied_on": "",
    }


def add_review_item(document: dict[str, Any], values: dict[str, Any], added_on: Optional[str] = None) -> tuple[dict[str, Any], list[str]]:
    item = build_added_item(document, values, added_on)
    errors = []
    for field in ["sequence", "canonical_text", "event_type", "location", "significance", "reason"]:
        if item.get(field) in {None, ""}:
            errors.append(f"Added item is missing {field}.")
    if errors:
        return document, errors

    updated = dict(document)
    updated["added_items"] = [*(updated.get("added_items") or []), item]
    return updated, []


def unknown_locations(values: list[str], known_locations: list[str]) -> list[str]:
    known = {name.strip().casefold() for name in known_locations if name.strip()}
    unknown = []
    seen = set()
    for value in values:
        location = str(value or "").strip()
        key = location.casefold()
        if not location or key in known or key in seen:
            continue
        seen.add(key)
        unknown.append(location)
    return unknown


def form_locations(form_values: dict[str, list[str]]) -> list[str]:
    return [*(form_values.get("location") or []), *(form_values.get("new_location") or [])]


def remove_added_item(document: dict[str, Any], item_id: str) -> tuple[dict[str, Any], list[str]]:
    if not item_id:
        return document, ["Missing added item id."]

    removed = False
    kept = []
    for item in document.get("added_items") or []:
        if item.get("id") == item_id:
            removed = True
            continue
        kept.append(item)

    if not removed:
        return document, [f"Added item not found: {item_id}."]

    updated = dict(document)
    updated["added_items"] = kept
    return updated, []


def update_review_document_from_form(document: dict[str, Any], form_values: dict[str, list[str]]) -> dict[str, Any]:
    updated = dict(document)
    item_ids = form_values.get("item_id") or []
    submitted = {}
    for index, item_id in enumerate(item_ids):
        section = _first(form_values, "section", index, "items")
        submitted[(section, item_id)] = {
            "sequence": _coerce_sequence(_first(form_values, "sequence", index)),
            "decision": _first(form_values, "decision", index, "pending"),
            "canonical_text": _first(form_values, "canonical_text", index),
            "event_type": _first(form_values, "event_type", index),
            "location": _first(form_values, "location", index),
            "significance": _coerce_significance(_first(form_values, "significance", index)),
            "reason": _first(form_values, "reason", index),
        }

    for section in ["items", "added_items"]:
        section_items = []
        for item in updated.get(section) or []:
            item = dict(item)
            patch = submitted.get((section, item.get("id")))
            if patch:
                changed = any(item.get(key) != value for key, value in patch.items())
                item.update(patch)
                if changed and item.get("applied_status") == "applied":
                    item["applied_status"] = "pending"
                    item["applied_on"] = ""
            section_items.append(item)
        updated[section] = section_items
    return updated


def reopen_review_document(document: dict[str, Any], reopened_on: Optional[str] = None) -> dict[str, Any]:
    if not document:
        return document
    if document.get("status") != "applied":
        return document

    updated = dict(document)
    updated["status"] = "in_review"
    updated["reopened_on"] = reopened_on or date.today().isoformat()
    return updated


def review_readiness_errors(document: dict[str, Any]) -> list[str]:
    errors = []
    counts = decision_counts(document)
    if counts["pending"]:
        errors.append(f"{counts['pending']} review item(s) still have pending decisions.")
    if counts["other"]:
        errors.append(f"{counts['other']} review item(s) have unknown decisions.")
    for note in validate_review_document(document):
        if note != "No review validation issues found.":
            errors.append(note)
    return errors


def mark_reviewed_document(document: dict[str, Any], reviewed_on: Optional[str] = None) -> tuple[dict[str, Any], list[str]]:
    errors = review_readiness_errors(document)
    if errors:
        return document, errors

    updated = dict(document)
    updated["status"] = "reviewed"
    updated["reviewed_on"] = reviewed_on or date.today().isoformat()
    return updated, []


def save_review_document(session_number: int, document: dict[str, Any]) -> Path:
    path = review_path(session_number)
    if not path.exists():
        raise FileNotFoundError(path)
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path

def validate_review_document(document: dict[str, Any]) -> list[str]:
    notes = []
    if not document:
        return ["Review file has not been initialized yet."]

    status = document.get("status") or ""
    if status not in VALID_STATUSES:
        notes.append(f"Review status is not recognized: {status or 'blank'}.")

    seen_sequences = set()
    seen_ids = set()
    for item in all_review_items(document):
        item_id = item.get("id") or ""
        if item_id in seen_ids:
            notes.append(f"Duplicate item id: {item_id}.")
        elif item_id:
            seen_ids.add(item_id)

        sequence = item.get("sequence")
        if sequence in seen_sequences:
            notes.append(f"Duplicate sequence value: {sequence}.")
        else:
            seen_sequences.add(sequence)

        decision = item.get("decision") or "pending"
        if decision not in VALID_DECISIONS:
            notes.append(f"{item_id or 'Item'} has unknown decision: {decision}.")
        if decision == "pending":
            notes.append(f"{item_id or 'Item'} still has a pending decision.")
        if decision in {"corrected", "added"}:
            for field in ["canonical_text", "event_type", "location", "significance", "reason"]:
                if item.get(field) in {None, ""}:
                    notes.append(f"{item_id or 'Item'} is {decision} but missing {field}.")

    if not notes:
        notes.append("No review validation issues found.")
    return notes
