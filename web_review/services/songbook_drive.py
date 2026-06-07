import json
from pathlib import Path
from typing import Any, Optional

from raglib.campaign import songbook_dir


MANIFEST_NAME = "drive_files.json"


def manifest_path() -> Path:
    return songbook_dir() / MANIFEST_NAME


def drive_manifest() -> dict[str, Any]:
    path = manifest_path()
    if not path.exists():
        return {"lyrics": [], "audio": [], "folders": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"lyrics": [], "audio": [], "folders": {}}
    return {
        "lyrics": sorted(data.get("lyrics") or [], key=lambda item: (item.get("title") or "").lower()),
        "audio": sorted(data.get("audio") or [], key=lambda item: (item.get("title") or "").lower()),
        "folders": data.get("folders") or {},
        "updated_at": data.get("updated_at") or "",
    }


def current_file_option(url: Optional[str], options: list[dict[str, Any]]) -> Optional[dict[str, str]]:
    value = (url or "").strip()
    if not value:
        return None
    if any((option.get("url") or "").strip() == value for option in options):
        return None
    return {"id": "", "title": "Current saved file", "url": value}
