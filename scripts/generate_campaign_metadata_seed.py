from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from raglib.campaign_metadata_seed import write_campaign_metadata_seed_sql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate campaign init SQL from campaign.yaml metadata.")
    parser.add_argument("--metadata", type=Path, default=None, help="Optional campaign.yaml path.")
    parser.add_argument("--output", type=Path, default=None, help="Optional output SQL path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = write_campaign_metadata_seed_sql(args.metadata, args.output)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
