
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import markdown
import yaml

from raglib import campaign


REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = campaign.campaign_root()
CLEAN_DIR = KNOWLEDGE_DIR / "clean"
FINAL_DIR = KNOWLEDGE_DIR / "final"
REVIEWS_DIR = KNOWLEDGE_DIR / "reviews"
RAW_DIR = KNOWLEDGE_DIR / "raw"

VALID_DECISIONS = {"pending", "accepted", "rejected", "corrected", "added"}
VALID_STATUSES = {"in_review", "reviewed", "applied"}
VALID_REVIEW_STAGES = {"compose_final_summary", "high_level_order", "bucketing", "event_resolution"}
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
    event_review_ready: bool
    missing_extraction_reviews: list[str]


EXTRACTION_REVIEW_FILES = [
    ("NPC Extraction", "session{session_number:02d}_npcs_reviewed.json"),
    ("Location Extraction", "session{session_number:02d}_locations_reviewed.json"),
    ("Artifact Extraction", "session{session_number:02d}_artifacts_reviewed.json"),
    ("Lore Item Extraction", "session{session_number:02d}_lore_items_reviewed.json"),
    ("Combat Encounter Extraction", "session{session_number:02d}_combat_encounters_reviewed.json"),
    ("Open Thread Extraction", "session{session_number:02d}_open_threads_reviewed.json"),
]


def session_key(session_number: int) -> str:
    return f"session{session_number:02d}"


def parse_session_ref(value: Any) -> int:
    match = re.search(r"(\d+)$", str(value or "").strip())
    if not match:
        raise ValueError(f"Could not parse session reference: {value!r}")
    return int(match.group(1))


def review_path(session_number: int) -> Path:
    return REVIEWS_DIR / f"{session_key(session_number)}_review.yaml"


def extraction_review_path(session_number: int, pattern: str) -> Path:
    return KNOWLEDGE_DIR / "extracted" / pattern.format(session_number=session_number)


def missing_extraction_reviews(session_number: int) -> list[str]:
    missing = []
    for label, pattern in EXTRACTION_REVIEW_FILES:
        if not extraction_review_path(session_number, pattern).exists():
            missing.append(label)
    return missing


def event_review_ready(session_number: int) -> bool:
    return not missing_extraction_reviews(session_number)


def event_review_access_blocked(session_number: int) -> bool:
    document = load_review_document(session_number)
    if (document.get("status") or "") in {"reviewed", "applied"} or final_summary_path(session_number).exists():
        return False
    return not event_review_ready(session_number)


def diary_path(session_number: int) -> Path:
    return CLEAN_DIR / f"{session_key(session_number)}_diary.md"


def draft_summary_path(session_number: int) -> Path:
    return CLEAN_DIR / f"{session_key(session_number)}_summary.md"


def final_summary_path(session_number: int) -> Path:
    return FINAL_DIR / f"{session_key(session_number)}_summary.md"


def raw_transcript_path(session_number: int) -> Path:
    return RAW_DIR / f"{session_key(session_number)}_transcript.txt"


def narrative_path(session_number: int) -> Path:
    return CLEAN_DIR / f"{session_key(session_number)}_narrative.md"


def spine_path(session_number: int) -> Path:
    return CLEAN_DIR / f"{session_key(session_number)}_spine.yaml"


def spine_validation_path(session_number: int) -> Path:
    return CLEAN_DIR / f"{session_key(session_number)}_spine_validation.md"


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
    status = document.get("status") or "unknown"
    if final_summary_mode(document):
        if final_summary_readiness_errors(document):
            return "compose-summary"
        if status == "in_review":
            return "mark-reviewed"
        if status in {"reviewed", "complete"}:
            return "apply"
        if status == "applied":
            return "done"
        return "inspect"
    counts = decision_counts(document)
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
    final_exists = final_summary_path(session_number).exists()
    status = document.get("status") or ("missing" if not document else "unknown")
    final_mode = final_summary_mode(document) or (final_exists and status == "applied")
    pending_decisions = 0 if final_mode else counts["pending"]
    missing_reviews = [] if status == "applied" or final_exists else missing_extraction_reviews(session_number)
    unapplied_items = 0 if final_mode else unapplied_count(document)
    next_action = "done" if final_exists and status == "applied" else next_action_for(document)
    if final_exists and status != "applied" and final_summary_mode(document):
        next_action = "inspect"
    return ReviewSummary(
        session=key,
        session_number=session_number,
        status=status,
        title=document.get("session_title") or "",
        path=str(path),
        review_exists=path.exists(),
        final_exists=final_exists,
        total_items=len(items) + len(added_items),
        base_items=len(items),
        added_items=len(added_items),
        pending_decisions=pending_decisions,
        accepted=counts["accepted"],
        rejected=counts["rejected"],
        corrected=counts["corrected"],
        added=counts["added"],
        unknown_decisions=counts["other"],
        unapplied_items=unapplied_items,
        next_action=next_action,
        event_review_ready=not missing_reviews,
        missing_extraction_reviews=missing_reviews,
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

    def decision_rank(item: dict[str, Any]) -> int:
        decision = item.get("decision") or "pending"
        if decision == "pending":
            return 0
        if decision not in VALID_DECISIONS:
            return 1
        return 2

    combined = []
    for section in ["items", "added_items"]:
        for item in document.get(section) or []:
            clone = dict(item)
            clone["section"] = section
            combined.append(clone)
    return sorted(combined, key=lambda item: (decision_rank(item), sequence_value(item)))


def review_stage(document: dict[str, Any]) -> str:
    if final_summary_mode(document):
        return "compose_final_summary"
    if (document.get("status") or "") in {"reviewed", "applied"}:
        return "event_resolution"
    stage = document.get("review_stage") or "high_level_order"
    if stage == "bucketing" and not document.get("macro_events"):
        return "high_level_order"
    return stage if stage in VALID_REVIEW_STAGES else "high_level_order"


def set_review_stage(document: dict[str, Any], stage: str) -> dict[str, Any]:
    if stage not in VALID_REVIEW_STAGES:
        return document
    updated = dict(document)
    updated["review_stage"] = stage
    return updated


def final_summary_mode(document: dict[str, Any]) -> bool:
    return bool(document.get("final_summary")) or document.get("review_stage") == "compose_final_summary"


def default_final_summary_for_session(session_number: int, document: dict[str, Any]) -> dict[str, Any]:
    timeline = document.get("timeline") or {}
    spine = {}
    if spine_path(session_number).exists():
        spine = yaml.safe_load(spine_path(session_number).read_text(encoding="utf-8")) or {}
    spine_timeline = spine.get("timeline") or {}
    existing = document.get("final_summary") or {}
    summary = (
        existing.get("summary_markdown")
        or read_text_if_exists(narrative_path(session_number))
        or read_text_if_exists(draft_summary_path(session_number))
    ).strip()
    return {
        "session_title": existing.get("session_title") or document.get("session_title") or f"Session {session_number:02d}",
        "real_world_date": existing.get("real_world_date") or document.get("session_date") or date.today().isoformat(),
        "in_world_date": existing.get("in_world_date") or document.get("in_game_date") or "N/A",
        "starting_location": existing.get("starting_location") or timeline.get("start_location") or spine_timeline.get("starting_location") or "",
        "ending_location": existing.get("ending_location") or timeline.get("end_location") or spine_timeline.get("ending_location") or "",
        "key_locations": existing.get("key_locations") or "",
        "major_outcome": existing.get("major_outcome") or "",
        "summary_markdown": summary,
    }


def final_summary_from_form(form_values: dict[str, list[str]], existing: dict[str, Any]) -> dict[str, Any]:
    def value(name: str) -> str:
        return _first(form_values, name, 0, str(existing.get(name) or "")).strip()

    return {
        "session_title": value("final_session_title"),
        "real_world_date": value("final_real_world_date"),
        "in_world_date": value("final_in_world_date") or "N/A",
        "starting_location": value("final_starting_location"),
        "ending_location": value("final_ending_location"),
        "key_locations": value("final_key_locations"),
        "major_outcome": value("final_major_outcome"),
        "summary_markdown": value("final_summary_markdown"),
    }


def update_final_summary_from_form(document: dict[str, Any], form_values: dict[str, list[str]]) -> dict[str, Any]:
    updated = dict(document)
    final_summary = final_summary_from_form(form_values, document.get("final_summary") or {})
    updated["review_stage"] = "compose_final_summary"
    updated["final_summary"] = final_summary
    updated["session_title"] = final_summary["session_title"]
    updated["session_date"] = final_summary["real_world_date"]
    updated["in_game_date"] = final_summary["in_world_date"]
    updated["primary_location"] = final_summary["ending_location"] or final_summary["starting_location"]
    updated["timeline"] = {
        "physical_date": final_summary["real_world_date"],
        "in_game_date": final_summary["in_world_date"] or "N/A",
        "start_location": final_summary["starting_location"],
        "end_location": final_summary["ending_location"],
    }
    if updated.get("status") == "applied":
        updated["status"] = "in_review"
    return updated


def final_summary_readiness_errors(document: dict[str, Any]) -> list[str]:
    final_summary = document.get("final_summary") or {}
    errors = []
    required = [
        ("session_title", "Session title"),
        ("real_world_date", "Real-world date"),
        ("in_world_date", "In-world date"),
        ("starting_location", "Starting location"),
        ("ending_location", "Ending location"),
        ("summary_markdown", "Canon final summary"),
    ]
    for field, label in required:
        if not str(final_summary.get(field) or "").strip():
            errors.append(f"{label} is required.")
    text = str(final_summary.get("summary_markdown") or "")
    if len(text.strip()) < 80:
        errors.append("Canon final summary is too short.")
    if re.search(r"\b(TODO|TBD|FIXME|TK)\b|\?\?\?", text, re.IGNORECASE):
        errors.append("Canon final summary contains unresolved placeholder text.")
    return errors


def filtered_review_items(items: list[dict[str, Any]], bucket: str = "") -> list[dict[str, Any]]:
    if not bucket or bucket == "all":
        return items
    if bucket == "unbucketed":
        return [
            item for item in items
            if not item.get("macro_event_id") and (item.get("decision") or "pending") != "rejected"
        ]
    if bucket == "rejected":
        return [item for item in items if (item.get("decision") or "pending") == "rejected"]
    return [item for item in items if item.get("macro_event_id") == bucket]


def sorted_macro_events(document: dict[str, Any]) -> list[dict[str, Any]]:
    def order_value(item: dict[str, Any]) -> float:
        try:
            return float(item.get("order") or 0)
        except (TypeError, ValueError):
            return 0.0

    return sorted([dict(item) for item in document.get("macro_events") or []], key=order_value)


def normalize_macro_event_orders(macro_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for index, item in enumerate(sorted_macro_events({"macro_events": macro_events}), start=1):
        normalized.append({**item, "order": index})
    return normalized


def macro_event_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in sorted_macro_events(document) if item.get("id")}


def bucket_counts(document: dict[str, Any]) -> dict[str, int]:
    counts = {"all": 0, "unbucketed": 0, "rejected": 0}
    for macro in sorted_macro_events(document):
        counts[macro["id"]] = 0
    for item in all_review_items(document):
        counts["all"] += 1
        decision = item.get("decision") or "pending"
        if decision == "rejected":
            counts["rejected"] += 1
            continue
        macro_id = item.get("macro_event_id") or ""
        if macro_id in counts:
            counts[macro_id] += 1
        else:
            counts["unbucketed"] += 1
    return counts


def bucketing_errors(document: dict[str, Any]) -> list[str]:
    counts = bucket_counts(document)
    if counts["unbucketed"]:
        return [f"{counts['unbucketed']} item(s) still need a bucket or rejection."]
    return []


def source_text(session_number: int, source: str) -> tuple[str, str]:
    choices = {
        "diary": ("Diary", diary_path(session_number)),
        "draft": ("Draft Summary", draft_summary_path(session_number)),
        "final": ("Final Summary", final_summary_path(session_number)),
        "narrative": ("Narrative Draft", narrative_path(session_number)),
        "spine": ("Session Spine", spine_path(session_number)),
        "spine_validation": ("Spine Validation", spine_validation_path(session_number)),
        "transcript": ("Raw Transcript", raw_transcript_path(session_number)),
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


def evidence_sources(session_number: int) -> list[dict[str, str]]:
    sources = [
        ("Narrative Draft", "narrative", narrative_path(session_number)),
        ("Session Spine", "spine", spine_path(session_number)),
        ("Draft Summary", "draft", draft_summary_path(session_number)),
        ("Spine Validation", "spine_validation", spine_validation_path(session_number)),
        ("Transcript", "transcript", raw_transcript_path(session_number)),
    ]
    evidence = []
    for label, key, path in sources:
        text = read_text_if_exists(path)
        if not text:
            continue
        evidence.append({
            "label": label,
            "source": key,
            "text": text,
            "html": render_markdown(text),
        })
    return evidence


def _entity_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    for key in [
        "canonical_name",
        "proposed_name",
        "name",
        "canonical_title",
        "proposed_title",
        "title",
        "encounter_name",
        "thread_title",
        "description",
    ]:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return json.dumps(item, ensure_ascii=False)[:120]


def _entity_note(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ["new_information", "description", "lore_significance", "evidence", "summary", "status"]:
        value = item.get(key)
        if isinstance(value, list):
            value = ", ".join(str(part) for part in value if str(part).strip())
        value = str(value or "").strip()
        if value:
            return value
    return ""


def entity_evidence(session_number: int) -> list[dict[str, Any]]:
    extracted_dir = KNOWLEDGE_DIR / "extracted"
    def row(item: Any, status: str) -> dict[str, str]:
        if isinstance(item, str):
            label = item
            note = ""
        else:
            label = _entity_label(item)
            note = _entity_note(item)
        return {
            "label": label,
            "note": note,
            "status": status,
        }

    specs = [
        ("NPCs", f"{session_key(session_number)}_npcs.json", f"{session_key(session_number)}_npcs_reviewed.json", {
            "known_npc_mentions": "known",
            "new_npc_candidates": "candidate",
            "rejected_candidates": "rejected",
        }),
        ("Locations", f"{session_key(session_number)}_locations.json", f"{session_key(session_number)}_locations_reviewed.json", {
            "known_location_mentions": "known",
            "new_location_candidates": "candidate",
            "rejected_candidates": "rejected",
        }),
        ("Artifacts", f"{session_key(session_number)}_artifacts.json", f"{session_key(session_number)}_artifacts_reviewed.json", {
            "known_artifact_mentions": "known",
            "new_artifact_candidates": "candidate",
            "rejected_candidates": "rejected",
        }),
        ("Lore", f"{session_key(session_number)}_lore_items.json", f"{session_key(session_number)}_lore_items_reviewed.json", {
            "known_lore_mentions": "known",
            "new_lore_item_candidates": "candidate",
            "new_lore_candidates": "candidate",
            "rejected_candidates": "rejected",
        }),
        ("Combat", f"{session_key(session_number)}_combat_encounters.json", f"{session_key(session_number)}_combat_encounters_reviewed.json", {
            "known_encounter_mentions": "known",
            "new_combat_encounter_candidates": "candidate",
            "combat_encounters": "candidate",
            "proposed_combat_encounters": "candidate",
            "rejected_candidates": "rejected",
        }),
        ("Open Threads", f"{session_key(session_number)}_open_threads.json", f"{session_key(session_number)}_open_threads_reviewed.json", {
            "known_open_thread_mentions": "known",
            "known_thread_mentions": "known",
            "new_open_thread_candidates": "candidate",
            "new_thread_candidates": "candidate",
            "open_threads": "candidate",
            "rejected_candidates": "rejected",
        }),
    ]
    groups = []
    for label, filename, reviewed_filename, keys in specs:
        path = extracted_dir / filename
        rows = []
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            for key, status in keys.items():
                for item in data.get(key) or []:
                    rows.append(row(item, status))
        reviewed_path = extracted_dir / reviewed_filename
        if reviewed_path.exists():
            try:
                reviewed_data = json.loads(reviewed_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                reviewed_data = {}
            for item in reviewed_data.get("applied") or []:
                rows.append(row(item, "applied"))
            for item in reviewed_data.get("skipped") or []:
                rows.append(row(item, "ignored"))
        if rows:
            groups.append({"label": label, "rows": rows})
    return groups


def session_workspace(session_number: int, source: str = "diary", source_view: str = "raw", bucket: str = "") -> dict[str, Any]:
    document = load_review_document(session_number)
    label, text = source_text(session_number, source)
    items = sorted_review_items(document)
    final_summary = default_final_summary_for_session(session_number, document) if document else {}
    validation_document = {**document, "final_summary": final_summary} if document else document
    return {
        "session_number": session_number,
        "session_key": session_key(session_number),
        "summary": summarize_review_document(session_number, document),
        "document": document,
        "items": filtered_review_items(items, bucket),
        "all_items": items,
        "macro_events": sorted_macro_events(document),
        "bucket_counts": bucket_counts(document),
        "selected_bucket": bucket or "all",
        "review_stage": "compose_final_summary" if document else review_stage(document),
        "source": source,
        "source_label": label,
        "source_text": text,
        "source_html": render_markdown(text),
        "source_view": source_view if source_view in {"raw", "print"} else "raw",
        "validation": validate_review_document(validation_document),
        "final_summary": final_summary,
        "summary_validation": final_summary_readiness_errors({"final_summary": final_summary}) if document else [],
        "final_exists": final_summary_path(session_number).exists(),
        "evidence_sources": evidence_sources(session_number),
        "entity_evidence": entity_evidence(session_number),
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


def _coerce_macro_order(value: Any) -> Any:
    return _coerce_sequence(value)


def next_macro_event_id(document: dict[str, Any]) -> str:
    highest = 0
    for item in document.get("macro_events") or []:
        match = re.search(r"macro-(\d+)$", str(item.get("id") or ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"macro-{highest + 1:03d}"


def update_macro_events_from_form(document: dict[str, Any], form_values: dict[str, list[str]]) -> dict[str, Any]:
    updated = dict(document)
    existing = {item.get("id"): dict(item) for item in document.get("macro_events") or [] if item.get("id")}
    macro_ids = form_values.get("macro_id") or []
    macro_events = []
    remove_ids = set(form_values.get("remove_macro_id") or [])
    seen_macro_ids = set()

    if macro_ids:
        for index, macro_id in enumerate(macro_ids):
            if not macro_id or macro_id in seen_macro_ids:
                continue
            seen_macro_ids.add(macro_id)
            description = _first(form_values, "macro_description", index).strip()
            location = _first(form_values, "macro_location", index).strip()
            order = _coerce_macro_order(_first(form_values, "macro_order", index))
            if macro_id in remove_ids or not (description or location or order):
                continue
            macro_events.append({
                **existing.get(macro_id, {}),
                "id": macro_id,
                "order": order,
                "description": description,
                "location": location,
            })
    else:
        macro_events = [
            dict(item)
            for item in document.get("macro_events") or []
            if item.get("id") not in remove_ids
        ]

    new_description = _first(form_values, "new_macro_description", 0).strip()
    new_location = _first(form_values, "new_macro_location", 0).strip()
    new_order = _coerce_macro_order(_first(form_values, "new_macro_order", 0))
    if new_description or new_location or new_order:
        macro_events.append({
            "id": next_macro_event_id(document),
            "order": new_order,
            "description": new_description,
            "location": new_location,
        })

    valid_ids = {item["id"] for item in macro_events}
    for section in ["items", "added_items"]:
        section_items = []
        for item in updated.get(section) or []:
            item = dict(item)
            if item.get("macro_event_id") not in valid_ids:
                item.pop("macro_event_id", None)
            section_items.append(item)
        updated[section] = section_items
    updated["macro_events"] = normalize_macro_event_orders(macro_events)
    next_stage = _first(form_values, "review_stage", 0)
    if next_stage in VALID_REVIEW_STAGES:
        updated["review_stage"] = next_stage
    return updated


def update_bucketing_from_form(document: dict[str, Any], form_values: dict[str, list[str]]) -> dict[str, Any]:
    updated = dict(document)
    macros = macro_event_map(document)
    item_ids = form_values.get("bucket_item_id") or []
    submitted = {}
    for index, item_id in enumerate(item_ids):
        submitted[item_id] = {
            "section": _first(form_values, "bucket_section", index, "items"),
            "macro_event_id": _first(form_values, "bucket_macro_event_id", index),
            "action": _first(form_values, "bucket_action", index),
        }

    for section in ["items", "added_items"]:
        section_items = []
        for item in updated.get(section) or []:
            item = dict(item)
            patch = submitted.get(item.get("id"))
            if patch and patch["section"] == section:
                if patch["action"] == "rejected":
                    item["decision"] = "rejected"
                    item["reason"] = item.get("reason") or "Rejected during bucketing pass."
                    item.pop("macro_event_id", None)
                    item.pop("macro_event_order", None)
                elif patch["macro_event_id"] in macros:
                    macro = macros[patch["macro_event_id"]]
                    item["macro_event_id"] = patch["macro_event_id"]
                    item["location"] = macro.get("location") or ""
                    if item.get("decision") == "rejected":
                        item["decision"] = "pending"
                if item.get("applied_status") == "applied":
                    item["applied_status"] = "pending"
                    item["applied_on"] = ""
            section_items.append(item)
        updated[section] = section_items

    next_stage = _first(form_values, "review_stage", 0)
    if next_stage in VALID_REVIEW_STAGES:
        updated["review_stage"] = next_stage
    return updated


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
    macros = macro_event_map(document)
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
            "macro_event_id": _first(form_values, "macro_event_id", index),
        }

    for section in ["items", "added_items"]:
        section_items = []
        for item in updated.get(section) or []:
            item = dict(item)
            patch = submitted.get((section, item.get("id")))
            if patch:
                changed = any(item.get(key) != value for key, value in patch.items())
                item.update(patch)
                macro = macros.get(item.get("macro_event_id") or "")
                if macro and item.get("decision") != "rejected":
                    item["location"] = macro.get("location") or item.get("location") or ""
                if changed and item.get("applied_status") == "applied":
                    item["applied_status"] = "pending"
                    item["applied_on"] = ""
            section_items.append(item)
        updated[section] = section_items
    return updated


def update_single_review_item_from_form(document: dict[str, Any], form_values: dict[str, list[str]], item_id: str) -> dict[str, Any]:
    filtered = {"item_id": [], "section": [], "sequence": [], "decision": [], "canonical_text": [], "event_type": [], "location": [], "significance": [], "reason": [], "macro_event_id": []}
    for index, submitted_id in enumerate(form_values.get("item_id") or []):
        if submitted_id != item_id:
            continue
        for key in filtered:
            filtered[key].append(_first(form_values, key, index))
        break
    if not filtered["item_id"]:
        return document
    return update_review_document_from_form(document, filtered)


def find_review_item(document: dict[str, Any], item_id: str) -> Optional[tuple[str, dict[str, Any]]]:
    for section in ["items", "added_items"]:
        for item in document.get(section) or []:
            if item.get("id") == item_id:
                return section, item
    return None


def update_batch_decision(document: dict[str, Any], item_ids: list[str], decision: str, reason: str = "", macro_event_id: str = "") -> tuple[dict[str, Any], list[str]]:
    if decision and decision not in VALID_DECISIONS - {"pending"}:
        return document, ["Choose an accepted, rejected, corrected, or added decision."]
    if not decision and not macro_event_id:
        return document, ["Choose a decision or bucket."]
    selected = {item_id for item_id in item_ids if item_id}
    if not selected:
        return document, ["Select at least one review item."]

    updated = dict(document)
    macro = macro_event_map(document).get(macro_event_id)
    changed = 0
    for section in ["items", "added_items"]:
        section_items = []
        for item in updated.get(section) or []:
            item = dict(item)
            if item.get("id") in selected:
                if decision:
                    item["decision"] = decision
                if reason:
                    item["reason"] = reason
                if macro_event_id:
                    item["macro_event_id"] = macro_event_id
                    if macro and item.get("decision") != "rejected":
                        item["location"] = macro.get("location") or item.get("location") or ""
                if item.get("applied_status") == "applied":
                    item["applied_status"] = "pending"
                    item["applied_on"] = ""
                changed += 1
            section_items.append(item)
        updated[section] = section_items
    if not changed:
        return document, ["Selected review items were not found."]
    return updated, []


def apply_macro_event_order(document: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    macros = sorted_macro_events(document)
    if not macros:
        return document, ["Create at least one high-level event bucket."]

    macro_by_id = {item["id"]: item for item in macros}
    updated = dict(document)
    sequence = 1
    assigned_ids = set()

    for macro in macros:
        bucket_items = []
        for section in ["items", "added_items"]:
            for item in updated.get(section) or []:
                if item.get("macro_event_id") == macro["id"]:
                    bucket_items.append(item)
        bucket_items = sorted(bucket_items, key=lambda item: float(item.get("sequence") or 0))
        for bucket_item in bucket_items:
            bucket_item["sequence"] = sequence
            bucket_item["location"] = macro.get("location") or bucket_item.get("location") or ""
            bucket_item["macro_event_order"] = macro.get("order")
            assigned_ids.add(bucket_item.get("id"))
            sequence += 1

    for section in ["items", "added_items"]:
        section_items = []
        for item in updated.get(section) or []:
            item = dict(item)
            if item.get("id") in assigned_ids:
                macro = macro_by_id.get(item.get("macro_event_id"))
                if macro:
                    item["macro_event_order"] = macro.get("order")
                    item["location"] = macro.get("location") or item.get("location") or ""
            section_items.append(item)
        updated[section] = section_items
    return updated, []


def merge_review_items(document: dict[str, Any], item_ids: list[str], values: dict[str, Any], merged_on: Optional[str] = None) -> tuple[dict[str, Any], list[str]]:
    selected = []
    for item_id in item_ids:
        found = find_review_item(document, item_id)
        if found:
            selected.append(found[1])
    if len(selected) < 2:
        return document, ["Select at least two review items to merge."]

    sequence_values = [_coerce_sequence(item.get("sequence")) for item in selected]
    numeric_sequences = [value for value in sequence_values if isinstance(value, (int, float))]
    merged_values = {
        "sequence": values.get("sequence") or (min(numeric_sequences) if numeric_sequences else ""),
        "canonical_text": values.get("canonical_text") or " ".join(item.get("canonical_text") or item.get("source_text") or "" for item in selected).strip(),
        "event_type": values.get("event_type") or next((item.get("event_type") for item in selected if item.get("event_type")), ""),
        "location": values.get("location") or next((item.get("location") for item in selected if item.get("location")), ""),
        "significance": values.get("significance") or max((item.get("significance") or 0 for item in selected), default=""),
        "reason": values.get("reason") or f"Merged from {', '.join(item.get('id') or 'unknown' for item in selected)}.",
    }
    updated, errors = add_review_item(document, merged_values, added_on=merged_on)
    if errors:
        return document, errors

    merged_id = (updated.get("added_items") or [])[-1]["id"]
    selected_ids = {item.get("id") for item in selected}
    for section in ["items", "added_items"]:
        section_items = []
        for item in updated.get(section) or []:
            item = dict(item)
            if item.get("id") in selected_ids:
                item["decision"] = "rejected"
                item["reason"] = f"Merged into {merged_id}."
                if item.get("applied_status") == "applied":
                    item["applied_status"] = "pending"
                    item["applied_on"] = ""
            section_items.append(item)
        updated[section] = section_items
    return updated, []


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
    if final_summary_mode(document):
        return final_summary_readiness_errors(document)
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

    if final_summary_mode(document):
        notes.extend(final_summary_readiness_errors(document))
        return notes or ["No review validation issues found."]

    seen_sequences = set()
    seen_ids = set()
    for item in all_review_items(document):
        item_id = item.get("id") or ""
        item_label = f"Order {item.get('sequence')} event {item_id}" if item.get("sequence") not in {None, ""} and item_id else item_id or "Item"
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
            notes.append(f"{item_label} has unknown decision: {decision}.")
        if decision == "pending":
            notes.append(f"{item_label} still has a pending decision.")
        if decision not in {"pending", "rejected"} and item.get("event_type") not in EVENT_TYPES:
            notes.append(f"{item_label} has decision {decision} but is missing a valid event type.")
        if decision in {"corrected", "added"}:
            for field in ["canonical_text", "significance", "reason"]:
                if item.get(field) in {None, ""}:
                    notes.append(f"{item_label} is {decision} but missing {field}.")

    if not notes:
        notes.append("No review validation issues found.")
    return notes
