from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import settings
from app.db import SessionLocal
from app.models.place import Place
from app.services.ingestion import ingest_google_place
from app.services.social_aggregation import recompute_social_aggregates
from app.services.social_ingestion import GooglePlaceDetailsClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich fallback places (no google_maps_uri) with Google Places API data."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Seconds between Google API calls to avoid rate limiting (default: 0.05).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of places to process (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print how many places would be enriched without calling the API.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if not settings.GOOGLE_MAPS_API_KEY:
        print("GOOGLE_MAPS_API_KEY is not set in .env", file=sys.stderr)
        return 1

    google_client = GooglePlaceDetailsClient(settings.GOOGLE_MAPS_API_KEY)

    db = SessionLocal()
    try:
        # Fallback places: have social mentions but were never Google-enriched.
        # google_maps_uri is always populated by ingest_google_place, so NULL means
        # the place was created as a minimal fallback during CSV import.
        query = db.query(Place).filter(
            Place.mention_count > 0,
            Place.google_maps_uri.is_(None),
        )
        if args.limit is not None:
            query = query.limit(args.limit)
        places = query.all()

        if args.dry_run:
            print(json.dumps({"would_enrich": len(places)}))
            return 0

        logger.info("Found %d fallback places to enrich", len(places))

        enriched = 0
        not_found = 0
        filtered_out = 0
        errors = 0
        enriched_place_ids: set[int] = set()

        for i, place in enumerate(places, 1):
            try:
                payload = google_client.fetch_place(place.google_place_id)
                if payload is None:
                    logger.info("[%d/%d] not found in Google: %s", i, len(places), place.google_place_id)
                    not_found += 1
                else:
                    result = ingest_google_place(db, payload)
                    action = result.get("action")
                    if result.get("place_id") is not None:
                        enriched += 1
                        enriched_place_ids.add(place.id)
                        logger.info("[%d/%d] %s → %s", i, len(places), place.display_name, action)
                    else:
                        filtered_out += 1
                        logger.info("[%d/%d] filtered out (non-Taipei): %s", i, len(places), place.display_name)
            except Exception:
                logger.exception("[%d/%d] error enriching %s", i, len(places), place.google_place_id)
                errors += 1

            if args.delay > 0:
                time.sleep(args.delay)

        if enriched_place_ids:
            logger.info("Recomputing social aggregates for %d enriched places...", len(enriched_place_ids))
            recompute_social_aggregates(db, place_ids=enriched_place_ids)

        stats = {
            "enriched": enriched,
            "not_found": not_found,
            "filtered_out": filtered_out,
            "error": errors,
        }
        print(json.dumps(stats))
        return 0

    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
