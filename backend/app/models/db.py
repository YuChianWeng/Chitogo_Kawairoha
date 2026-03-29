from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiosqlite

from app.config import get_settings

logger = logging.getLogger(__name__)

_DB_PATH: Optional[str] = None


def _db_path() -> str:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = get_settings().db_path
    return _DB_PATH


# ---------------------------------------------------------------------------
# Domain entity
# ---------------------------------------------------------------------------


@dataclass
class Venue:
    venue_id: str
    name: str
    district: str
    category: str
    address: str
    lat: float
    lng: float
    indoor: bool
    cost_level: str  # "low" | "medium" | "high"
    avg_duration_minutes: int
    tags: list[str] = field(default_factory=list)
    trend_score: float = 0.5
    opening_hour: int = 9   # 24h
    closing_hour: int = 21  # 24h


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_VENUES = """
CREATE TABLE IF NOT EXISTS venues (
    venue_id            TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    district            TEXT NOT NULL,
    category            TEXT NOT NULL,
    address             TEXT NOT NULL,
    lat                 REAL NOT NULL,
    lng                 REAL NOT NULL,
    indoor              INTEGER NOT NULL DEFAULT 0,
    cost_level          TEXT NOT NULL DEFAULT 'medium',
    avg_duration_minutes INTEGER NOT NULL DEFAULT 60,
    tags                TEXT NOT NULL DEFAULT '[]',
    trend_score         REAL NOT NULL DEFAULT 0.5,
    opening_hour        INTEGER NOT NULL DEFAULT 9,
    closing_hour        INTEGER NOT NULL DEFAULT 21
)
"""


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(_CREATE_VENUES)
        await db.commit()
    logger.info("Database initialised at %s", _db_path())


async def seed_from_json(json_path: str) -> int:
    """Insert venues from a JSON file; skip rows that already exist."""
    path = Path(json_path)
    if not path.exists():
        logger.warning("Seed file not found: %s", json_path)
        return 0

    with path.open() as fh:
        records = json.load(fh)

    inserted = 0
    async with aiosqlite.connect(_db_path()) as db:
        for r in records:
            tags_json = json.dumps(r.get("tags", []))
            await db.execute(
                """
                INSERT OR IGNORE INTO venues
                    (venue_id, name, district, category, address, lat, lng,
                     indoor, cost_level, avg_duration_minutes, tags,
                     trend_score, opening_hour, closing_hour)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    r["venue_id"],
                    r["name"],
                    r["district"],
                    r["category"],
                    r["address"],
                    r["lat"],
                    r["lng"],
                    int(r.get("indoor", False)),
                    r.get("cost_level", "medium"),
                    r.get("avg_duration_minutes", 60),
                    tags_json,
                    r.get("trend_score", 0.5),
                    r.get("opening_hour", 9),
                    r.get("closing_hour", 21),
                ),
            )
            inserted += 1
        await db.commit()

    logger.info("Seeded %d venues from %s", inserted, json_path)
    return inserted


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def _row_to_venue(row: aiosqlite.Row) -> Venue:
    return Venue(
        venue_id=row[0],
        name=row[1],
        district=row[2],
        category=row[3],
        address=row[4],
        lat=row[5],
        lng=row[6],
        indoor=bool(row[7]),
        cost_level=row[8],
        avg_duration_minutes=row[9],
        tags=json.loads(row[10]),
        trend_score=row[11],
        opening_hour=row[12],
        closing_hour=row[13],
    )


async def get_all_venues() -> list[Venue]:
    async with aiosqlite.connect(_db_path()) as db:
        async with db.execute(
            "SELECT venue_id,name,district,category,address,lat,lng,"
            "indoor,cost_level,avg_duration_minutes,tags,trend_score,"
            "opening_hour,closing_hour FROM venues"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_venue(r) for r in rows]


async def filter_venues(
    district: Optional[str] = None,
    indoor_pref: Optional[str] = None,   # "indoor" | "outdoor" | "both"
    cost_level: Optional[str] = None,
    interests: Optional[list[str]] = None,
) -> list[Venue]:
    """Return venues matching the given filters.

    Falls back gracefully: if too few results (<3), relax district then
    indoor_pref so there is always something to work with.
    """
    all_venues = await get_all_venues()

    def _matches(v: Venue, strict_district: bool, strict_indoor: bool) -> bool:
        if strict_district and district and v.district != district:
            return False
        if strict_indoor and indoor_pref and indoor_pref != "both":
            wanted_indoor = indoor_pref == "indoor"
            if v.indoor != wanted_indoor:
                return False
        if cost_level and v.cost_level != cost_level:
            return False
        return True

    # Strict pass
    results = [v for v in all_venues if _matches(v, True, True)]

    # Relax indoor constraint
    if len(results) < 3:
        results = [v for v in all_venues if _matches(v, True, False)]

    # Relax district constraint (city-wide)
    if len(results) < 3:
        results = [v for v in all_venues if _matches(v, False, False)]

    return results
