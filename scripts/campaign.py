#!/usr/bin/env python3
"""Manage campaign profile folders."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.campaign import campaign_root, ensure_campaign_dirs


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise SystemExit("Campaign name must contain at least one letter or number.")
    return slug


def init_campaign(name: str, display_name: str | None = None) -> Path:
    campaign_id = slugify(name)
    root = campaign_root(campaign_id)
    ensure_campaign_dirs(campaign_id)
    metadata = root / "campaign.yaml"
    if not metadata.exists():
        title = display_name or name.strip() or campaign_id.replace("_", " ").title()
        metadata.write_text(
            "\n".join([
                "campaign:",
                f"  id: {campaign_id}",
                f"  name: {title}",
                f"  archive_title: The {title} Archivum",
                "  archive_subtitle: A campaign canon archive of sessions, lore, people, places, artifacts, and unresolved threads.",
                "  description: New campaign archive.",
                "",
                "database:",
                f"  name: {campaign_id}",
                "  user: admin",
                "  password: gofaban",
                "  port: 5432",
                "",
                "dm:",
                "  name: unknown",
                "",
                "party: []",
                "",
                "glossary: []",
                "",
                "features:",
                "  songbook: false",
                "",
            ]),
            encoding="utf-8",
        )
    else:
        document = yaml.safe_load(metadata.read_text(encoding="utf-8")) or {}
        features = document.setdefault("features", {})
        if "songbook" not in features and "songbook" not in document:
            features["songbook"] = False
            metadata.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage local campaign profiles.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="Create a campaign profile folder.")
    init.add_argument("name", help="Campaign id/name, e.g. shadowed_isles.")
    init.add_argument("--display-name", default=None, help="Human-readable campaign name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "init":
        root = init_campaign(args.name, args.display_name)
        print(f"Campaign profile ready: {root}")
        print(f"Use with: FARRLIND_CAMPAIGN={root.name}")


if __name__ == "__main__":
    main()
