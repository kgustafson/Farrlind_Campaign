#!/usr/bin/env python3
"""Download public songbook lyrics/docs and MP3s into local song folders."""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from raglib.campaign import campaign_path


REPO_ROOT = Path(__file__).resolve().parents[1]
SONGBOOK_MD = campaign_path("clean", "The Revealed Songbook of Faban Colon.md")
SONGBOOK_DIR = campaign_path("songbook")


@dataclass
class SongAsset:
    number: int
    title: str
    lyrics_url: str
    mp3_url: str
    folder: str


FOLDER_OVERRIDES = {
    19: "Mihiras_Rise",
}


def folder_name(number: int, title: str) -> str:
    if number in FOLDER_OVERRIDES:
        return FOLDER_OVERRIDES[number]

    cleaned = re.sub(r"\([^)]*\)", "", title)
    cleaned = cleaned.replace("&", "and")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def extract_doc_id(url: str) -> str:
    match = re.search(r"/document/(?:u/\d+/)?d/([^/]+)", url)
    if not match:
        raise ValueError(f"Could not parse Google Doc id from {url}")
    return match.group(1)


def extract_drive_id(url: str) -> str:
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("id")
    if query_id:
        return query_id[0]

    match = re.search(r"/file/d/([^/]+)", url)
    if match:
        return match.group(1)

    raise ValueError(f"Could not parse Drive id from {url}")


def parse_assets(markdown: str) -> list[SongAsset]:
    in_index = False
    assets: list[SongAsset] = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line == "**Songbook Index**":
            in_index = True
            continue
        if not in_index or not line.startswith("| **"):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 6:
            continue

        number_match = re.search(r"\*\*(\d+)\*\*", cells[0])
        lyrics_match = re.search(r"\[[^\]]+\]\(([^)]+)\)", cells[4])
        mp3_match = re.search(r"\[[^\]]+\]\(([^)]+)\)", cells[5])
        if not number_match or not lyrics_match or not mp3_match:
            continue

        number = int(number_match.group(1))
        title = re.sub(r"\s+", " ", cells[1]).strip()
        assets.append(
            SongAsset(
                number=number,
                title=title,
                lyrics_url=lyrics_match.group(1),
                mp3_url=mp3_match.group(1),
                folder=folder_name(number, title),
            )
        )

    return assets


def fetch(opener, url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(request, timeout=60) as response:
        return response.read()


def download_doc_as_markdown(opener, url: str) -> str:
    doc_id = extract_doc_id(url)
    export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    data = fetch(opener, export_url)
    text = data.decode("utf-8", errors="replace").strip()
    if "<html" in text[:200].lower():
        raise RuntimeError("Google Docs returned HTML instead of exported text")
    return text + "\n"


def drive_confirm_token(page: bytes) -> str | None:
    text = page.decode("utf-8", errors="ignore")
    patterns = [
        r"confirm=([0-9A-Za-z_]+)",
        r'name="confirm"\s+value="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return html.unescape(match.group(1))
    return None


def download_drive_file(opener, url: str) -> bytes:
    file_id = extract_drive_id(url)
    direct_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    data = fetch(opener, direct_url)

    if data[:20].lower().startswith(b"<!doctype html") or b"download_warning" in data[:2000]:
        token = drive_confirm_token(data)
        if token:
            confirmed_url = f"{direct_url}&confirm={token}"
            data = fetch(opener, confirmed_url)

    if data[:20].lower().startswith(b"<!doctype html"):
        raise RuntimeError("Google Drive returned HTML instead of file bytes")

    return data


def write_file(path: Path, data: bytes | str, overwrite: bool) -> str:
    if path.exists() and not overwrite:
        return "kept"

    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return "wrote"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    markdown = SONGBOOK_MD.read_text(encoding="utf-8")
    assets = parse_assets(markdown)
    opener = build_opener(HTTPCookieProcessor())

    print(f"Found {len(assets)} song assets")
    failures = []

    for asset in assets:
        folder = SONGBOOK_DIR / asset.folder
        lyrics_path = folder / "lyrics.md"
        mp3_path = folder / "song.mp3"
        print(f"{asset.number:02d} {asset.title} -> {folder.relative_to(REPO_ROOT)}")

        if args.dry_run:
            continue

        try:
            lyrics = download_doc_as_markdown(opener, asset.lyrics_url)
            lyrics_status = write_file(lyrics_path, lyrics, overwrite=args.overwrite)
            time.sleep(0.2)

            mp3 = download_drive_file(opener, asset.mp3_url)
            mp3_status = write_file(mp3_path, mp3, overwrite=args.overwrite)
            time.sleep(0.2)

            print(f"   lyrics: {lyrics_status}; mp3: {mp3_status}")
        except (HTTPError, URLError, RuntimeError, ValueError) as exc:
            failures.append((asset.number, asset.title, str(exc)))
            print(f"   ERROR: {exc}", file=sys.stderr)

    if failures:
        print("\nFailures:", file=sys.stderr)
        for number, title, error in failures:
            print(f"- {number:02d} {title}: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
