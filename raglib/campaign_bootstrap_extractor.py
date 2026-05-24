import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from raglib import campaign
from raglib.io_utils import read_text, write_text
from raglib.ollama_client import generate
from raglib.prompts import load_prompt


DEFAULT_MODEL = "gemma4:e2b"
DEFAULT_SESSION_LIMIT = 3
OLLAMA_OPTIONS = {
    "temperature": 0.1,
    "top_p": 0.9,
    "num_ctx": 32768,
}
EXPECTED_TOP_LEVEL_KEYS = [
    "campaign_candidates",
    "dm_candidates",
    "party_candidates",
    "glossary_candidates",
    "rejected_candidates",
    "uncertainties",
]
SOURCE_PRIORITY = [
    "final_summary",
    "curated_packet",
    "draft_summary",
    "diary",
    "transcript",
]
VALID_CONFIDENCE = {"high", "medium", "low"}


def output_path() -> Path:
    return campaign.extracted_dir() / "campaign_bootstrap.json"


def metadata_output_path() -> Path:
    return campaign.extracted_dir() / "campaign_bootstrap_metadata.json"


def session_number(session_name: str) -> int:
    match = re.search(r"(\d+)$", session_name or "")
    if not match:
        raise ValueError(f"Could not parse session number from {session_name!r}")
    return int(match.group(1))


def session_name(number: int) -> str:
    return f"session{number:02d}"


def normalize_session_name(value: str) -> str:
    return session_name(session_number(value))


def source_candidates(name: str) -> list[tuple[str, Path]]:
    return [
        ("final_summary", campaign.final_dir() / f"{name}_summary.md"),
        ("curated_packet", campaign.clean_dir() / f"{name}_curated.md"),
        ("draft_summary", campaign.clean_dir() / f"{name}_summary.md"),
        ("diary", campaign.clean_dir() / f"{name}_diary.md"),
        ("transcript", campaign.raw_dir() / f"{name}_transcript.txt"),
    ]


def available_session_names(limit: int = DEFAULT_SESSION_LIMIT) -> list[str]:
    discovered = set()
    patterns = [
        (campaign.final_dir(), r"session(\d+)_summary\.md$"),
        (campaign.clean_dir(), r"session(\d+)_(?:summary|diary|curated)\.md$"),
        (campaign.raw_dir(), r"session(\d+)_transcript\.txt$"),
    ]
    for folder, pattern in patterns:
        if not folder.exists():
            continue
        for path in folder.iterdir():
            match = re.match(pattern, path.name)
            if match:
                discovered.add(int(match.group(1)))
    return [session_name(number) for number in sorted(discovered)[:limit]]


def load_campaign_metadata() -> dict[str, Any]:
    path = campaign.campaign_metadata_path()
    if not path.exists():
        return {}
    return yaml.safe_load(read_text(path)) or {}


def load_session_sources(session_names: list[str], source: str = "auto") -> list[dict[str, str]]:
    loaded: list[dict[str, str]] = []
    for raw_name in session_names:
        name = normalize_session_name(raw_name)
        candidates = source_candidates(name)
        if source == "auto":
            existing = [(label, path) for label, path in candidates if path.exists()]
            if not existing:
                continue
            selected = []
            by_label = dict(existing)
            for label in SOURCE_PRIORITY:
                path = by_label.get(label)
                if path:
                    selected.append((label, path))
                if len(selected) == 2:
                    break
        else:
            by_label = dict(candidates)
            if source not in by_label:
                raise ValueError(f"Unsupported campaign bootstrap source: {source}")
            selected = [(source, by_label[source])] if by_label[source].exists() else []

        for label, path in selected:
            loaded.append({
                "session": name,
                "label": label,
                "path": str(path),
                "text": read_text(path),
            })

    if not loaded:
        raise FileNotFoundError("No source files found for campaign bootstrap extraction.")
    return loaded


def build_prompt(sources: list[dict[str, str]], campaign_metadata: dict[str, Any]) -> str:
    source_blocks = []
    for source in sources:
        source_blocks.append(
            f"--- SOURCE {source['session']} {source['label']} ({source['path']}) START ---\n"
            f"{source['text'].strip()}\n"
            f"--- SOURCE {source['session']} {source['label']} END ---"
        )
    return "\n\n".join([
        load_prompt("extract_campaign_bootstrap").strip(),
        "Active campaign name:",
        campaign.active_campaign_name(),
        "Current campaign metadata JSON:",
        json.dumps(campaign_metadata, indent=2, ensure_ascii=False),
        "Early session source material:",
        "\n\n".join(source_blocks),
    ])


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start:end + 1])


def normalize_confidence(value: Any) -> str:
    confidence = str(value or "").strip().lower()
    return confidence if confidence in VALID_CONFIDENCE else "medium"


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_candidate_fields(candidate: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    normalized = {field: str(candidate.get(field) or "").strip() for field in fields}
    normalized["confidence"] = normalize_confidence(candidate.get("confidence"))
    normalized["evidence"] = str(candidate.get("evidence") or "").strip()
    return normalized


def normalize_extraction(document: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    campaign_candidates = document.get("campaign_candidates")
    normalized["campaign_candidates"] = campaign_candidates if isinstance(campaign_candidates, dict) else {}
    for key in ["name", "archive_title", "archive_subtitle"]:
        value = normalized["campaign_candidates"].get(key)
        if not isinstance(value, dict):
            value = {}
        normalized["campaign_candidates"][key] = normalize_candidate_fields(value, ["value"])

    list_keys = ["dm_candidates", "party_candidates", "glossary_candidates", "rejected_candidates", "uncertainties"]
    for key in list_keys:
        value = document.get(key, [])
        normalized[key] = value if isinstance(value, list) else []

    normalized["dm_candidates"] = [
        normalize_candidate_fields(item, ["name"])
        for item in normalized["dm_candidates"]
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]

    party = []
    for item in normalized["party_candidates"]:
        if not isinstance(item, dict):
            continue
        candidate = normalize_candidate_fields(
            item,
            ["character_name", "full_name", "player_name", "race", "class", "subclass", "notes"],
        )
        candidate["aliases"] = normalize_string_list(item.get("aliases"))
        if candidate["character_name"] or candidate["player_name"]:
            party.append(candidate)
    normalized["party_candidates"] = party

    glossary = []
    for item in normalized["glossary_candidates"]:
        if not isinstance(item, dict):
            continue
        candidate = normalize_candidate_fields(item, ["term", "note"])
        candidate["aliases"] = normalize_string_list(item.get("aliases"))
        if candidate["term"]:
            glossary.append(candidate)
    normalized["glossary_candidates"] = glossary

    normalized["rejected_candidates"] = [
        {
            "text": str(item.get("text") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
        }
        for item in normalized["rejected_candidates"]
        if isinstance(item, dict) and (item.get("text") or item.get("reason"))
    ]
    normalized["uncertainties"] = [
        {
            "candidate": str(item.get("candidate") or "").strip(),
            "issue": str(item.get("issue") or "").strip(),
            "needs_human_decision": bool(item.get("needs_human_decision", True)),
        }
        for item in normalized["uncertainties"]
        if isinstance(item, dict) and (item.get("candidate") or item.get("issue"))
    ]
    return normalized


def extract_campaign_bootstrap(
    session_names: Optional[list[str]] = None,
    model: Optional[str] = None,
    source: str = "auto",
) -> Path:
    model = model or os.environ.get("FARRLIND_CAMPAIGN_BOOTSTRAP_MODEL", DEFAULT_MODEL)
    session_names = [normalize_session_name(name) for name in session_names] if session_names else available_session_names()
    if not session_names:
        raise FileNotFoundError("No early sessions found for campaign bootstrap extraction.")
    sources = load_session_sources(session_names, source=source)
    metadata = load_campaign_metadata()
    prompt = build_prompt(sources, metadata)

    print(f"Extracting campaign bootstrap candidates for {campaign.active_campaign_name()} with {model}...")
    started = time.monotonic()
    raw_output = generate(prompt, model=model, timeout=1800, options=OLLAMA_OPTIONS)
    duration = time.monotonic() - started
    extracted = normalize_extraction(extract_json_object(raw_output))

    path = output_path()
    write_text(path, json.dumps(extracted, indent=2, ensure_ascii=False) + "\n")
    meta_path = metadata_output_path()
    write_text(meta_path, json.dumps({
        "campaign": campaign.active_campaign_name(),
        "model": model,
        "source": source,
        "sessions": session_names,
        "sources": [{"session": item["session"], "label": item["label"], "path": item["path"], "chars": len(item["text"])} for item in sources],
        "campaign_metadata": str(campaign.campaign_metadata_path()),
        "duration_seconds": round(duration, 2),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(path),
    }, indent=2) + "\n")
    print(f"Campaign bootstrap extraction written to: {path}")
    print(f"Campaign bootstrap metadata written to: {meta_path}")
    return path
