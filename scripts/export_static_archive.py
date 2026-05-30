#!/usr/bin/env python3
"""Export the read-only campaign archive as static files."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.campaign import active_campaign_name, assets_dir, campaign_feature_enabled, campaign_path

DEFAULT_OUTPUT_DIR = REPO_ROOT / "dist" / "archive"
DEFAULT_BASE_URL = "http://127.0.0.1:8002"
WORLD_MAP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class ExportError(RuntimeError):
    pass


def fetch_text(base_url: str, path: str, query: dict[str, str] | None = None) -> str:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.status != 200:
                raise ExportError(f"{url} returned HTTP {response.status}")
            return response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ExportError(f"Could not fetch {url}: {exc}") from exc


def fetch_json(base_url: str, path: str):
    return json.loads(fetch_text(base_url, path))


def static_page_path(output_dir: Path, route: str) -> Path:
    route = route.split("?", 1)[0].strip()
    if route in {"", "/"}:
        return output_dir / "index.html"
    return output_dir / route.strip("/") / "index.html"


def write_static_page(output_dir: Path, route: str, html: str) -> Path:
    path = static_page_path(output_dir, route)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def campaign_world_map_path() -> Path | None:
    assets = assets_dir()
    for suffix in sorted(WORLD_MAP_EXTENSIONS):
        candidate = assets / f"world-map{suffix}"
        if candidate.exists():
            return candidate
    return None


def static_world_map_path() -> str | None:
    path = campaign_world_map_path()
    return f"/media/world-map{path.suffix.lower()}" if path else None


def rewrite_html(html: str) -> str:
    html = re.sub(r'https?://[^/"\']+/static/', "/static/", html)
    html = re.sub(r'method="post" action="[^"]+"', 'method="get" action="#"', html)
    html = re.sub(
        r'(/sessions/(session\d+)/review)\?source=diary[^" ]*',
        r"/sessions/\2/diary/",
        html,
    )
    html = re.sub(
        r'(/sessions/(session\d+)/review)\?source=(?:final|summary)[^" ]*',
        r"/sessions/\2/summary/",
        html,
    )
    html = re.sub(
        r'(/sessions/(session\d+)/review)(["#])',
        r"/sessions/\2/summary/\3",
        html,
    )
    html = re.sub(
        r'(/sessions/(session\d+)/review)(?=[?"])',
        r"/sessions/\2/summary/",
        html,
    )
    html = re.sub(r'(/songbook/(\d+)/lyrics)(?=["?#])', r"/songbook/\2/lyrics/", html)
    world_map = static_world_map_path()
    if world_map:
        html = re.sub(r"/world-map/image\?v=\d+", world_map, html)
        html = html.replace("/world-map/image", world_map)

    def audio_replacement(match: re.Match[str]) -> str:
        song_number = int(match.group(1))
        return f"/media/songbook/{song_number:02d}/song.mp3"

    html = re.sub(r"/songbook/(\d+)/audio", audio_replacement, html)
    return html


def copy_static_assets(output_dir: Path) -> None:
    source = REPO_ROOT / "web_review" / "static"
    destination = output_dir / "static"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def resolve_repo_media_path(path_value: str) -> Path:
    source = Path(path_value)
    if not source.is_absolute():
        source = REPO_ROOT / source
    if source.exists():
        return source

    legacy_path = Path(path_value)
    legacy_prefix = Path("knowledge") / "Faban"
    if not legacy_path.is_absolute() and legacy_path.parts[:2] == legacy_prefix.parts:
        migrated = campaign_path(*legacy_path.parts[2:])
        if migrated.exists():
            return migrated
    return source


def copy_songbook_media(output_dir: Path, songs: list[dict]) -> int:
    copied = 0
    for song in songs:
        song_number = int(song["song_number"])
        mp3_path = song.get("mp3_local_path")
        if not mp3_path:
            continue
        source = resolve_repo_media_path(mp3_path)
        if not source.exists():
            continue
        destination = output_dir / "media" / "songbook" / f"{song_number:02d}" / "song.mp3"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
    return copied


def copy_world_map_media(output_dir: Path) -> int:
    source = campaign_world_map_path()
    if source is None:
        return 0
    destination = output_dir / "media" / f"world-map{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return 1


def discover_session_keys(index_html: str) -> list[str]:
    return sorted(set(re.findall(r"/sessions/(session\d+)/review", index_html)))


def export_archive(base_url: str = DEFAULT_BASE_URL, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    copy_static_assets(output_dir)
    copied_world_maps = copy_world_map_media(output_dir)

    exported_pages: list[str] = []

    primary_routes = [
        "/",
        "/npcs",
        "/locations",
        "/artifacts",
        "/lore-items",
        "/combat-encounters",
        "/open-threads",
        "/timeline",
    ]
    if campaign_feature_enabled("songbook", default=False):
        primary_routes.insert(-1, "/songbook")

    index_html = ""
    for route in primary_routes:
        raw_html = fetch_text(base_url, route)
        html = rewrite_html(raw_html)
        write_static_page(output_dir, route, html)
        exported_pages.append(route)
        if route == "/":
            index_html = raw_html

    for session_key in discover_session_keys(index_html):
        diary_html = rewrite_html(fetch_text(base_url, f"/sessions/{session_key}/review", {"source": "diary"}))
        summary_html = rewrite_html(fetch_text(base_url, f"/sessions/{session_key}/review", {"source": "final"}))
        write_static_page(output_dir, f"/sessions/{session_key}/diary", diary_html)
        write_static_page(output_dir, f"/sessions/{session_key}/summary", summary_html)
        exported_pages.extend([f"/sessions/{session_key}/diary", f"/sessions/{session_key}/summary"])

    songs = []
    copied_audio = 0
    if campaign_feature_enabled("songbook", default=False):
        songs = fetch_json(base_url, "/api/songbook")
        for song in songs:
            song_number = int(song["song_number"])
            if not song.get("has_local_lyrics"):
                continue
            html = rewrite_html(fetch_text(base_url, f"/songbook/{song_number}/lyrics"))
            write_static_page(output_dir, f"/songbook/{song_number}/lyrics", html)
            exported_pages.append(f"/songbook/{song_number}/lyrics")

        copied_audio = copy_songbook_media(output_dir, songs)
    file_count = sum(1 for path in output_dir.rglob("*") if path.is_file())
    byte_count = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    manifest = {
        "source": f"{active_campaign_name()}_archive_app",
        "output_dir": "dist/archive",
        "page_count": len(exported_pages),
        "file_count": file_count,
        "byte_count": byte_count,
        "song_audio_files": copied_audio,
        "world_map_files": copied_world_maps,
        "pages": exported_pages,
    }
    (output_dir / "static-export-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the campaign archive as static HTML for Netlify.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Archive app base URL to snapshot.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Static archive output directory.")
    args = parser.parse_args()
    try:
        manifest = export_archive(args.base_url, args.output_dir)
    except ExportError as exc:
        print(f"Static archive export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Static archive exported to {manifest['output_dir']}")
    print(f"Pages: {manifest['page_count']}")
    print(f"Files: {manifest['file_count']}")
    print(f"Song audio files: {manifest['song_audio_files']}")
    print(f"Bytes: {manifest['byte_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
