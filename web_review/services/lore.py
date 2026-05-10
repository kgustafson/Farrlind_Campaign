from __future__ import annotations

from pathlib import Path

from web_review.services import reviews


LORE_DIR = reviews.REPO_ROOT / "knowledge" / "Faban" / "lore"
WELLS_OF_MAGIC_PATH = LORE_DIR / "wells_of_magic.md"


def read_wells_of_magic() -> str:
    try:
        return WELLS_OF_MAGIC_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_wells_of_magic(text: str, path: Path = WELLS_OF_MAGIC_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
