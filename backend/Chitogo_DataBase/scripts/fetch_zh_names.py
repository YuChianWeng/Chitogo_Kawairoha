"""Backfill name_zh for places that currently only have an English name.

Uses the Google Places API (New) Place Details endpoint with languageCode=zh-TW.

Usage:
    python scripts/fetch_zh_names.py [--limit N] [--delay SECONDS] [--dry-run]

Options:
    --limit N        Process at most N places (default: all)
    --delay SECONDS  Sleep between API calls in seconds (default: 0.12 ≈ 8 QPS)
    --dry-run        Fetch and print results without writing to DB
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib import error, request as urllib_request
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.models  # noqa: F401
from app.db import SessionLocal, engine
from app.models.place import Place
from sqlalchemy import text

PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
FIELD_MASK = "displayName"


def _fetch_zh_name(api_key: str, google_place_id: str) -> str | None:
    url = PLACE_DETAILS_URL.format(place_id=google_place_id) + "?languageCode=zh-TW"
    req = urllib_request.Request(
        url,
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            display_name = data.get("displayName", {})
            if isinstance(display_name, dict):
                return display_name.get("text")
            return None
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code} for {google_place_id}: {body[:200]}", file=sys.stderr)
        return None
    except error.URLError as exc:
        print(f"  URL error for {google_place_id}: {exc}", file=sys.stderr)
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Max places to process")
    parser.add_argument("--delay", type=float, default=0.12, help="Seconds between API calls (default: 0.12)")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to DB")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Missing GOOGLE_MAPS_API_KEY environment variable", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        query = db.query(Place.id, Place.google_place_id, Place.display_name).filter(
            Place.name_zh.is_(None)
        )
        if args.limit:
            query = query.limit(args.limit)
        targets = query.all()
    finally:
        db.close()

    total = len(targets)
    if total == 0:
        print("No places missing name_zh. Nothing to do.")
        return 0

    print(f"Places to process: {total}" + (" (dry-run)" if args.dry_run else ""))
    print(f"API delay: {args.delay}s between calls\n")

    updated = 0
    not_found = 0
    errors = 0

    for i, (place_id, google_place_id, display_name) in enumerate(targets, 1):
        zh_name = _fetch_zh_name(api_key, google_place_id)

        if zh_name is None:
            print(f"[{i}/{total}] SKIP  {google_place_id} ({display_name}) — no zh name returned")
            not_found += 1
        elif args.dry_run:
            print(f"[{i}/{total}] DRY   {display_name!r} → {zh_name!r}")
            updated += 1
        else:
            db = SessionLocal()
            try:
                db.execute(
                    text("UPDATE places SET name_zh = :zh, display_name = :zh WHERE id = :id"),
                    {"zh": zh_name, "id": place_id},
                )
                db.commit()
                print(f"[{i}/{total}] OK    {display_name!r} → {zh_name!r}")
                updated += 1
            except Exception as exc:
                db.rollback()
                print(f"[{i}/{total}] ERROR writing {place_id}: {exc}", file=sys.stderr)
                errors += 1
            finally:
                db.close()

        if i < total:
            time.sleep(args.delay)

    print(f"\nDone. updated={updated} not_found={not_found} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
