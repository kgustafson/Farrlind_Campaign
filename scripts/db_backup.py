import subprocess
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from raglib.campaign import active_campaign_name, campaign_container_name, campaign_database_name


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups"
INCOMPATIBLE_DUMP_LINES = {
    "SET transaction_timeout = 0;\n",
}


def pg_dump_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg2://")
    return database_url


def default_backup_path(backup_dir: Path = DEFAULT_BACKUP_DIR, now: Optional[datetime] = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return backup_dir / f"{active_campaign_name()}_{timestamp}.sql"


def sanitize_backup_file(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered = [line for line in lines if line not in INCOMPATIBLE_DUMP_LINES]
    if filtered != lines:
        path.write_text("".join(filtered), encoding="utf-8")


def backup_database(
    output_path: Optional[Path] = None,
    *,
    container: str = "",
    user: str = "admin",
    database: str = "",
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
            container or campaign_container_name(),
            "pg_dump",
            "--clean",
            "--if-exists",
            "-U",
            user,
            "-d",
            database or campaign_database_name(),
        ]
    with path.open("wb") as output:
        subprocess.run(command, stdout=output, check=True)
    sanitize_backup_file(path)
    return path
