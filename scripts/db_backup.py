import subprocess
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups"


def pg_dump_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg2://")
    return database_url


def default_backup_path(backup_dir: Path = DEFAULT_BACKUP_DIR, now: Optional[datetime] = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return backup_dir / f"farrlind_{timestamp}.sql"


def backup_database(
    output_path: Optional[Path] = None,
    *,
    container: str = "farrlind_db",
    user: str = "admin",
    database: str = "farrlind",
) -> Path:
    path = output_path or default_backup_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    database_url = os.getenv("FARRLIND_DATABASE_URL")
    if database_url and shutil.which("pg_dump"):
        command = ["pg_dump", "--clean", "--if-exists", pg_dump_url(database_url)]
    else:
        command = [
            "docker",
            "exec",
            container,
            "pg_dump",
            "--clean",
            "--if-exists",
            "-U",
            user,
            "-d",
            database,
        ]
    with path.open("wb") as output:
        subprocess.run(command, stdout=output, check=True)
    return path
