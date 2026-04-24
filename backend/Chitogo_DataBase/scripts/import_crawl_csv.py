from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings
from app.db import SessionLocal
from app.services.social_ingestion import GooglePlaceDetailsClient, import_crawl_csv


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import crawler CSV mentions into the Place Data Service."
    )
    parser.add_argument("csv_path", help="Path to the crawler CSV file.")
    parser.add_argument(
        "--source",
        choices=("ifoodie", "taipei_spots"),
        help="Optional source hint for mixed CSV schemas.",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip Google Place Details enrichment and use DB hit or fallback insert only.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    csv_path = Path(args.csv_path)
    if not csv_path.is_file():
        print(f"File not found: {csv_path}", file=sys.stderr)
        return 1

    google_client = None
    if not args.no_enrich and settings.GOOGLE_MAPS_API_KEY:
        google_client = GooglePlaceDetailsClient(settings.GOOGLE_MAPS_API_KEY)

    db = SessionLocal()
    try:
        stats = import_crawl_csv(
            db,
            csv_path,
            source_hint=args.source,
            google_client=google_client,
        )
        print(json.dumps(stats.as_dict(), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"Fatal import error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
