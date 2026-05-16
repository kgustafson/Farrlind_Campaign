
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from web_review import db
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
        sys.executable,
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


def run_health(timeout: Optional[int] = 120) -> CommandResult:
    command = [
        sys.executable,
        str(reviews.REPO_ROOT / "scripts" / "dm_query.py"),
        "health",
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


def run_smoke_test(base_url: str = "http://127.0.0.1:8000", timeout: float = 3.0) -> CommandResult:
    checks: list[str] = []
    errors: list[str] = []
    started = time.monotonic()

    for path, expected in [
        ("/", "Session Review Ledger"),
        ("/timeline", "Campaign Timeline"),
        ("/open-threads", "Open Threads"),
        ("/api/timeline", "session_count"),
    ]:
        url = f"{base_url.rstrip('/')}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                status = response.status
        except (urllib.error.URLError, TimeoutError) as exc:
            errors.append(f"{path}: request failed ({exc})")
            continue
        if status != 200:
            errors.append(f"{path}: expected HTTP 200, got {status}")
        elif expected not in body:
            errors.append(f"{path}: missing expected text '{expected}'")
        else:
            checks.append(f"{path}: ok")

    try:
        rows = db.fetch_all("SELECT count(*) AS session_count FROM session;")
        session_count = rows[0]["session_count"] if rows else 0
    except Exception as exc:  # pragma: no cover - defensive display for operator utility
        errors.append(f"database: query failed ({exc})")
    else:
        if session_count:
            checks.append(f"database: {session_count} sessions")
        else:
            errors.append("database: no sessions found")

    elapsed = time.monotonic() - started
    if errors:
        stdout = f"Smoke test failed in {elapsed:.2f}s.\n" + "\n".join(errors)
        if checks:
            stdout += "\n\nPassed checks:\n" + "\n".join(checks)
        return CommandResult(1, stdout, "")
    return CommandResult(0, f"Smoke test passed in {elapsed:.2f}s. " + "; ".join(checks), "")


def apply_review(session_number: int) -> CommandResult:
    return run_review_command("apply-review", session_number)


def write_final_summary(session_number: int) -> CommandResult:
    return run_review_command("write-final-summary", session_number)
