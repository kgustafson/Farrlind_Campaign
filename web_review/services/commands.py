
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
    route_checks = [
        ("Routes", "/", "Session Review Ledger"),
        ("Routes", "/timeline", "Campaign Timeline"),
        ("Routes", "/open-threads", "Open Threads"),
        ("API", "/api/timeline", "session_count"),
    ]
    passed: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    started = time.monotonic()

    for category, path, expected in route_checks:
        url = f"{base_url.rstrip('/')}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                status = response.status
        except (urllib.error.URLError, TimeoutError) as exc:
            errors.append((category, f"{path}: request failed ({exc})"))
            continue
        if status != 200:
            errors.append((category, f"{path}: expected HTTP 200, got {status}"))
        elif expected not in body:
            errors.append((category, f"{path}: missing expected text '{expected}'"))
        else:
            passed.append((category, f"{path}: ok"))

    try:
        rows = db.fetch_all("SELECT count(*) AS session_count FROM session;")
        session_count = rows[0]["session_count"] if rows else 0
    except Exception as exc:  # pragma: no cover - defensive display for operator utility
        errors.append(("Database", f"session count query failed ({exc})"))
    else:
        if session_count:
            passed.append(("Database", f"session count query: {session_count} sessions"))
        else:
            errors.append(("Database", "session count query returned no sessions"))

    elapsed = time.monotonic() - started
    total = len(passed) + len(errors)
    categories = sorted({category for category, _detail in [*passed, *errors]})
    lines = [
        f"Smoke test {'failed' if errors else 'passed'} in {elapsed:.2f}s.",
        f"Tests run: {total}",
        f"Passed: {len(passed)}",
        f"Failed: {len(errors)}",
        f"Categories: {', '.join(categories)}",
        "",
        "Details:",
    ]
    for category in categories:
        lines.append(f"- {category}")
        for _passed_category, detail in [item for item in passed if item[0] == category]:
            lines.append(f"  PASS {detail}")
        for _error_category, detail in [item for item in errors if item[0] == category]:
            lines.append(f"  FAIL {detail}")
    return CommandResult(1 if errors else 0, "\n".join(lines), "")


def apply_review(session_number: int) -> CommandResult:
    return run_review_command("apply-review", session_number)


def write_final_summary(session_number: int) -> CommandResult:
    return run_review_command("write-final-summary", session_number)
