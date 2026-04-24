from __future__ import annotations

import csv
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Protocol
from urllib import error, parse, request
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.place_social_mention import PlaceSocialMention
from app.models.place_source_google import PlaceSourceGoogle
from app.services.ingestion import (
    TAIPEI_ALLOWED_DISTRICTS,
    TAIPEI_DISTRICT_NAME_MAP,
    ingest_google_place,
    normalize_district_name,
)
from app.services.social_aggregation import recompute_social_aggregates

logger = logging.getLogger(__name__)

TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
GOOGLE_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{}"
GOOGLE_DETAILS_FIELD_MASK = ",".join(
    [
        "id",
        "displayName",
        "primaryType",
        "types",
        "formattedAddress",
        "addressComponents",
        "location",
        "rating",
        "userRatingCount",
        "priceLevel",
        "businessStatus",
        "googleMapsUri",
        "websiteUri",
        "nationalPhoneNumber",
        "regularOpeningHours",
    ]
)
TAIPEI_CITY_MARKERS = ("台北", "臺北", "taipei")
TAG_PRECISION = Decimal("0.01")
DISTRICT_MATCH_CANDIDATES = sorted(
    {
        *TAIPEI_ALLOWED_DISTRICTS,
        *TAIPEI_DISTRICT_NAME_MAP.keys(),
        *TAIPEI_DISTRICT_NAME_MAP.values(),
    },
    key=len,
    reverse=True,
)
MULTI_UNDERSCORE_RE = re.compile(r"_+")
NON_WORD_RE = re.compile(r"[^\w]+", flags=re.UNICODE)


class SupportsGooglePlaceDetails(Protocol):
    def fetch_place(self, google_place_id: str) -> dict | None:
        ...


@dataclass(slots=True)
class CrawlMention:
    external_id: str
    google_place_id: str
    platform: str
    location: str
    address: str | None
    source_url: str | None
    original_text: str | None
    sentiment_score: Decimal | None
    crowdedness: Decimal | None
    vibe_tags: list[str]
    posted_at: datetime | None
    raw_row: dict[str, str] = field(repr=False)


@dataclass(slots=True)
class ImportStats:
    db_hit: int = 0
    google_enriched: int = 0
    fallback_inserted: int = 0
    filtered_out: int = 0
    duplicate_mention: int = 0
    error: int = 0
    touched_place_ids: set[int] = field(default_factory=set, repr=False)

    def as_dict(self) -> dict[str, int]:
        return {
            "db_hit": self.db_hit,
            "google_enriched": self.google_enriched,
            "fallback_inserted": self.fallback_inserted,
            "filtered_out": self.filtered_out,
            "duplicate_mention": self.duplicate_mention,
            "error": self.error,
        }


class GooglePlaceDetailsClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_place(self, google_place_id: str) -> dict | None:
        url = GOOGLE_PLACE_DETAILS_URL.format(parse.quote(google_place_id, safe=""))
        req = request.Request(
            url,
            headers={
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": GOOGLE_DETAILS_FIELD_MASK,
            },
            method="GET",
        )

        try:
            with request.urlopen(req) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError:
            return None
        except error.URLError:
            return None

        if not isinstance(payload, dict):
            return None

        payload.setdefault("id", google_place_id)
        return payload


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold().strip()


def _strip_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    return normalized or None


def normalize_platform(value: object, *, source_hint: str | None = None) -> str | None:
    platform = _strip_optional_text(value)
    if platform is None and source_hint is not None:
        platform = _strip_optional_text(source_hint)
    if platform is None:
        return None
    return platform.casefold().replace(" ", "_")


def normalize_vibe_tag(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = NON_WORD_RE.sub("_", normalized)
    normalized = MULTI_UNDERSCORE_RE.sub("_", normalized).strip("_")
    return normalized


def parse_vibe_tags(value: object) -> list[str]:
    raw_value = _strip_optional_text(value)
    if raw_value is None:
        return []

    raw_tags: list[object]
    if raw_value.startswith("["):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            raw_tags = parsed
        else:
            raw_tags = raw_value.split(",")
    else:
        raw_tags = raw_value.split(",")

    normalized_tags: list[str] = []
    seen_tags: set[str] = set()
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, str):
            continue
        normalized_tag = normalize_vibe_tag(raw_tag)
        if not normalized_tag or normalized_tag in seen_tags:
            continue
        seen_tags.add(normalized_tag)
        normalized_tags.append(normalized_tag)
    return normalized_tags


def parse_posted_at(value: object) -> datetime | None:
    raw_value = _strip_optional_text(value)
    if raw_value is None:
        return None

    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        try:
            parsed = datetime.strptime(raw_value, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"invalid created_at: {raw_value}") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TAIPEI_TIMEZONE)
    return parsed


def parse_score(value: object) -> Decimal | None:
    raw_value = _strip_optional_text(value)
    if raw_value is None:
        return None

    try:
        score = Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid score value: {raw_value}") from exc

    return score.quantize(TAG_PRECISION, rounding=ROUND_HALF_UP)


def parse_crawl_row(
    row: dict[str, object], *, source_hint: str | None = None
) -> CrawlMention:
    google_place_id = _strip_optional_text(row.get("google_place_id")) or _strip_optional_text(
        row.get("place_id")
    )
    if google_place_id is None:
        raise ValueError("google_place_id is required")

    external_id = _strip_optional_text(row.get("id"))
    if external_id is None:
        raise ValueError("external_id is required")

    platform = normalize_platform(row.get("platform"), source_hint=source_hint)
    if platform is None:
        raise ValueError("platform is required")

    location = _strip_optional_text(row.get("location")) or google_place_id

    return CrawlMention(
        external_id=external_id,
        google_place_id=google_place_id,
        platform=platform,
        location=location,
        address=_strip_optional_text(row.get("address")),
        source_url=_strip_optional_text(row.get("source_url")),
        original_text=_strip_optional_text(row.get("original_text")),
        sentiment_score=parse_score(row.get("sentiment_score")),
        crowdedness=parse_score(row.get("crowdedness")),
        vibe_tags=parse_vibe_tags(row.get("vibe_tags")),
        posted_at=parse_posted_at(row.get("created_at")),
        raw_row={
            str(key): "" if value is None else str(value) for key, value in row.items()
        },
    )


def extract_taipei_district(address: str | None) -> str | None:
    normalized_address = _strip_optional_text(address)
    if normalized_address is None:
        return None

    normalized_address = unicodedata.normalize("NFKC", normalized_address)
    if not any(marker in normalized_address.casefold() for marker in TAIPEI_CITY_MARKERS):
        return None

    canonical_address = (
        normalized_address.casefold().replace("’", "").replace("'", "")
    )
    for candidate, district in TAIPEI_DISTRICT_NAME_MAP.items():
        canonical_candidate = candidate.casefold().replace("’", "").replace("'", "")
        if canonical_candidate in canonical_address:
            return district

    for candidate in DISTRICT_MATCH_CANDIDATES:
        if candidate in TAIPEI_ALLOWED_DISTRICTS and candidate in normalized_address:
            district = normalize_district_name(candidate)
            if district in TAIPEI_ALLOWED_DISTRICTS:
                return district
    return None


def _find_place_by_google_place_id(db: Session, google_place_id: str) -> Place | None:
    return db.query(Place).filter_by(google_place_id=google_place_id).first()


def _find_existing_mention(
    db: Session, *, platform: str, external_id: str
) -> PlaceSocialMention | None:
    return (
        db.query(PlaceSocialMention)
        .filter_by(platform=platform, external_id=external_id)
        .first()
    )


def _append_raw_source_record(db: Session, mention: CrawlMention) -> None:
    existing_raw_record = (
        db.query(PlaceSourceGoogle)
        .filter_by(google_place_id=mention.google_place_id)
        .first()
    )
    if existing_raw_record is not None:
        return

    db.add(
        PlaceSourceGoogle(
            google_place_id=mention.google_place_id,
            raw_json=mention.raw_row,
            fetched_at=utc_now(),
        )
    )


def _create_fallback_place(
    db: Session, mention: CrawlMention, *, district: str
) -> Place:
    place = Place(
        google_place_id=mention.google_place_id,
        display_name=mention.location,
        normalized_name=_normalize_name(mention.location),
        formatted_address=mention.address,
        district=district,
        internal_category="other",
        mention_count=0,
        last_synced_at=utc_now(),
    )
    db.add(place)
    db.flush()
    return place


def _resolve_place(
    db: Session,
    mention: CrawlMention,
    *,
    google_client: SupportsGooglePlaceDetails | None,
) -> tuple[Place | None, str]:
    existing_place = _find_place_by_google_place_id(db, mention.google_place_id)
    if existing_place is not None:
        return existing_place, "db_hit"

    google_ingestion_ran = False
    if google_client is not None:
        try:
            google_payload = google_client.fetch_place(mention.google_place_id)
        except Exception:
            google_payload = None
        if google_payload:
            google_payload.setdefault("id", mention.google_place_id)
            google_ingestion_ran = True
            result = ingest_google_place(db, google_payload)
            if result.get("place_id") is not None:
                enriched_place = _find_place_by_google_place_id(db, mention.google_place_id)
                if enriched_place is not None:
                    return enriched_place, "google_enriched"

    district = extract_taipei_district(mention.address)
    if district is None:
        if not google_ingestion_ran:
            _append_raw_source_record(db, mention)
        return None, "filtered_out"

    fallback_place = _create_fallback_place(db, mention, district=district)
    return fallback_place, "fallback_inserted"


def _add_social_mention(db: Session, mention: CrawlMention, *, place_id: int) -> None:
    db.add(
        PlaceSocialMention(
            place_id=place_id,
            platform=mention.platform,
            source_url=mention.source_url,
            original_text=mention.original_text,
            sentiment_score=mention.sentiment_score,
            crowdedness=mention.crowdedness,
            vibe_tags=mention.vibe_tags or None,
            posted_at=mention.posted_at,
            external_id=mention.external_id,
        )
    )

def import_crawl_csv(
    db: Session,
    csv_path: str | Path,
    *,
    source_hint: str | None = None,
    google_client: SupportsGooglePlaceDetails | None = None,
) -> ImportStats:
    path = Path(csv_path)
    stats = ImportStats()

    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            try:
                mention = parse_crawl_row(row, source_hint=source_hint)

                if _find_existing_mention(
                    db, platform=mention.platform, external_id=mention.external_id
                ):
                    stats.duplicate_mention += 1
                    continue

                place, resolution = _resolve_place(
                    db, mention, google_client=google_client
                )

                if resolution == "filtered_out":
                    stats.filtered_out += 1
                    db.commit()
                    continue

                if place is None:
                    raise ValueError("place resolution returned no place")

                if resolution == "db_hit":
                    stats.db_hit += 1
                elif resolution == "google_enriched":
                    stats.google_enriched += 1
                elif resolution == "fallback_inserted":
                    stats.fallback_inserted += 1

                _add_social_mention(db, mention, place_id=place.id)
                db.commit()
                stats.touched_place_ids.add(place.id)
            except Exception:
                logger.exception(
                    "error processing row %s (platform=%s)",
                    row.get("id"),
                    row.get("platform"),
                )
                db.rollback()
                stats.error += 1

    if stats.touched_place_ids:
        recompute_social_aggregates(db, place_ids=stats.touched_place_ids)

    return stats
