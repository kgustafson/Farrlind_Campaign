from pathlib import Path
from raglib.config import ENCODING


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding=ENCODING)


def write_text(path: Path, content: str):
    ensure_dir(path.parent)
    path.write_text(content, encoding=ENCODING)


def append_text(path: Path, content: str):
    ensure_dir(path.parent)
    with open(path, "a", encoding=ENCODING) as f:
        f.write(content)


def file_exists(path: Path) -> bool:
    return path.exists()


def list_files(path: Path):
    if not path.exists():
        return []
    return list(path.iterdir())
