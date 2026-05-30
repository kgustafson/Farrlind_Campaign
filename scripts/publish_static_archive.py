#!/usr/bin/env python3
"""Export the archive and sync it into the static-site git repository."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.export_static_archive import DEFAULT_BASE_URL, DEFAULT_OUTPUT_DIR, export_archive

DEFAULT_STATIC_REPO = Path("/Volumes/T7_WORK/Farrlind_Static_Archive")
DEFAULT_GIT_USER_NAME = "Kurt Gustafson"
DEFAULT_GIT_USER_EMAIL = "kgustafson2@gmail.com"


class PublishError(RuntimeError):
    pass


def run_git(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        check=False,
        capture_output=True,
        text=True,
    )


def git_config_value(repo_path: Path, key: str) -> str:
    result = run_git(repo_path, ["config", "--get", key])
    return result.stdout.strip() if result.returncode == 0 else ""


def ensure_git_identity(repo_path: Path) -> None:
    name = (
        git_config_value(repo_path, "user.name")
        or os.getenv("STATIC_ARCHIVE_GIT_USER_NAME", "").strip()
        or os.getenv("GIT_AUTHOR_NAME", "").strip()
        or DEFAULT_GIT_USER_NAME
    )
    email = (
        git_config_value(repo_path, "user.email")
        or os.getenv("STATIC_ARCHIVE_GIT_USER_EMAIL", "").strip()
        or os.getenv("GIT_AUTHOR_EMAIL", "").strip()
        or DEFAULT_GIT_USER_EMAIL
    )
    for key, value in [("user.name", name), ("user.email", email)]:
        configured = run_git(repo_path, ["config", "--local", key, value])
        if configured.returncode != 0:
            raise PublishError(configured.stderr.strip() or f"Could not set git {key}.")


def require_clean_repo(repo_path: Path) -> None:
    status = run_git(repo_path, ["status", "--short"])
    if status.returncode != 0:
        raise PublishError(status.stderr.strip() or "Could not inspect static archive git status.")
    if status.stdout.strip():
        raise PublishError(
            "Static archive repository has uncommitted changes. Commit, stash, or clear them before publishing."
        )


def clear_static_repo(repo_path: Path) -> None:
    for child in repo_path.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_export_to_repo(export_dir: Path, repo_path: Path) -> None:
    clear_static_repo(repo_path)
    for child in export_dir.iterdir():
        destination = repo_path / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def publish_static_archive(
    static_repo: Path = DEFAULT_STATIC_REPO,
    base_url: str = DEFAULT_BASE_URL,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    message: str = "Update Farrlind static archive",
    push: bool = False,
) -> str:
    static_repo = static_repo.resolve()
    output_dir = output_dir.resolve()
    if not (static_repo / ".git").exists():
        raise PublishError(f"{static_repo} is not a git repository.")

    ensure_git_identity(static_repo)
    manifest = export_archive(base_url=base_url, output_dir=output_dir)
    copy_export_to_repo(output_dir, static_repo)

    run_git(static_repo, ["add", "-A"])
    status = run_git(static_repo, ["status", "--short"])
    if status.returncode != 0:
        raise PublishError(status.stderr.strip() or "Could not inspect generated static archive changes.")
    if not status.stdout.strip():
        return "\n".join([
            "Static archive export completed.",
            "No git changes detected in the static archive repository.",
            f"Pages: {manifest['page_count']}",
            f"Files: {manifest['file_count']}",
            f"Song audio files: {manifest['song_audio_files']}",
        ])

    commit = run_git(static_repo, ["commit", "-m", message])
    if commit.returncode != 0:
        raise PublishError(commit.stderr.strip() or commit.stdout.strip() or "Static archive git commit failed.")

    lines = [
        "Static archive exported and committed.",
        f"Repository: {static_repo}",
        f"Commit: {commit.stdout.strip()}",
        f"Pages: {manifest['page_count']}",
        f"Files: {manifest['file_count']}",
        f"Song audio files: {manifest['song_audio_files']}",
        f"Bytes: {manifest['byte_count']}",
    ]
    if push:
        pushed = run_git(static_repo, ["push"])
        if pushed.returncode != 0:
            raise PublishError(pushed.stderr.strip() or pushed.stdout.strip() or "Static archive git push failed.")
        lines.append("Pushed to origin.")
    else:
        lines.append("Push skipped. Run git push from the static archive repo when ready.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the Farrlind static archive into its git repository.")
    parser.add_argument("--static-repo", type=Path, default=DEFAULT_STATIC_REPO, help="Static archive git repository.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Archive app base URL to snapshot.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Temporary static export output dir.")
    parser.add_argument("--message", default="Update Farrlind static archive", help="Git commit message.")
    parser.add_argument("--push", action="store_true", help="Push the generated commit to origin.")
    args = parser.parse_args()
    try:
        print(publish_static_archive(
            static_repo=args.static_repo,
            base_url=args.base_url,
            output_dir=args.output_dir,
            message=args.message,
            push=args.push,
        ))
    except PublishError as exc:
        print(f"Static archive publish failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
