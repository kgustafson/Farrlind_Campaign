
import subprocess
from dataclasses import dataclass
from typing import Optional

from web_review.services import reviews


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_review_command(action: str, session_number: int, timeout: Optional[int] = 120) -> CommandResult:
    if action not in {"apply-review", "write-final-summary"}:
        raise ValueError(f"Unsupported review command: {action}")
    command = [
        str(reviews.REPO_ROOT / "rag-env" / "bin" / "python"),
        str(reviews.REPO_ROOT / "scripts" / "dm_query.py"),
        action,
        reviews.session_key(session_number),
    ]
    completed = subprocess.run(
        command,
        cwd=str(reviews.REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def apply_review(session_number: int) -> CommandResult:
    return run_review_command("apply-review", session_number)


def write_final_summary(session_number: int) -> CommandResult:
    return run_review_command("write-final-summary", session_number)
