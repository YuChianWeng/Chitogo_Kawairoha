"""Aggregator: fetch from all providers, normalize, merge, deduplicate.

Runtime data flow:
  1. Check TTL cache for each provider
  2. Fetch from Google Places + Crawler in parallel (if cache miss)
  3. Normalize district names from coordinates
  4. Merge results into one list
  5. Deduplicate by venue name similarity + proximity
  6. Apply basic filters (district, indoor_pref, cost)
  7. If both external sources fail or return empty -> fallback to local seed data
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Optional

from app.config import get_settings
from app.models.db import Venue, filter_venues as seed_filter_venues
from app.providers.base import DISTRICT_CENTRES, district_centre
from app.providers.cache import TTLCache, make_cache_key
from app.providers.crawler import CrawlerProvider
from app.providers.google_places import GooglePlacesProvider

logger = logging.getLogger(__name__)

# Module-level singleton cache and providers
_cache: TTLCache | None = None
_google: GooglePlacesProvider | None = None
_crawler: CrawlerProvider | None = None


def _get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        ttl = get_settings().candidate_cache_ttl_minutes * 60
        _cache = TTLCache(ttl_seconds=ttl)
    return _cache


def _get_google() -> GooglePlacesProvider:
    global _google
    if _google is None:
        _google = GooglePlacesProvider()
    return _google


def _get_crawler() -> CrawlerProvider:
    global _crawler
    if _crawler is None:
        _crawler = CrawlerProvider()
    return _crawler


# ---- District assignment from coordinates ----

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _assign_district(venue: Venue) -> Venue:
    """Assign the nearest Taipei district based on coordinates."""
    if venue.district:
        return venue
    best_dist = float("inf")
    best_name = "Zhongzheng"  # fallback
    for name, (clat, clng) in DISTRICT_CENTRES.items():
        d = _haversine_km(venue.lat, venue.lng, clat, clng)
        if d < best_dist:
            best_dist = d
            best_name = name
    venue.district = best_name
    return venue


# ---- Deduplication ----

def _normalize_name(name: str) -> str:
    return name.lower().strip().replace("'", "").replace("-", " ")


def _is_duplicate(a: Venue, b: Venue) -> bool:
    """Two venues are duplicates if they share a very similar name or
    are within 50m of each other."""
    if _normalize_name(a.name) == _normalize_name(b.name):
        return True
    dist = _haversine_km(a.lat, a.lng, b.lat, b.lng)
    if dist < 0.05:  # 50 metres
        return True
    return False


def _deduplicate(venues: list[Venue]) -> list[Venue]:
    """Keep the first occurrence; merge trend_score by taking the max."""
    unique: list[Venue] = []
    for v in venues:
        dup_found = False
        for u in unique:
            if _is_duplicate(v, u):
                u.trend_score = max(u.trend_score, v.trend_score)
                # Merge tags
                for tag in v.tags:
                    if tag not in u.tags and len(u.tags) < 5:
                        u.tags.append(tag)
                dup_found = True
                break
        if not dup_found:
            unique.append(v)
    return unique


# ---- Filtering (light, matches existing pipeline expectations) ----

def _basic_filter(
    venues: list[Venue],
    district: str,
    indoor_pref: Optional[str] = None,
    cost_level: Optional[str] = None,
) -> list[Venue]:
    """Filter by district proximity, indoor pref, and cost. Relax if < 3."""
    centre = district_centre(district)

    def _in_range(v: Venue) -> bool:
        return v.district == district or _haversine_km(v.lat, v.lng, *centre) <= 3.0

    def _indoor_ok(v: Venue, strict: bool) -> bool:
        if not strict or not indoor_pref or indoor_pref == "both":
            return True
        return v.indoor == (indoor_pref == "indoor")

    def _cost_ok(v: Venue) -> bool:
        if not cost_level:
            return True
        return v.cost_level == cost_level

    # Strict
    result = [v for v in venues if _in_range(v) and _indoor_ok(v, True) and _cost_ok(v)]
    if len(result) >= 3:
        return result

    # Relax indoor
    result = [v for v in venues if _in_range(v) and _cost_ok(v)]
    if len(result) >= 3:
        return result

    # Relax district (all venues)
    result = [v for v in venues if _cost_ok(v)]
    if len(result) >= 3:
        return result

    return venues


# ---- Public API ----

async def fetch_candidates(
    district: str,
    interests: list[str],
    indoor_pref: Optional[str] = None,
    cost_level: Optional[str] = None,
) -> tuple[list[Venue], bool]:
    """Fetch, merge, and filter candidate venues.

    Returns:
        (venues, used_fallback) — used_fallback is True if we fell back to
        local seed data because external sources failed or returned too few.
    """
    cache = _get_cache()
    centre_lat, centre_lng = district_centre(district)

    # --- Try cache first ---
    google_key = make_cache_key("google", district, interests)
    crawler_key = make_cache_key("crawler", district, interests)

    google_cached = cache.get(google_key)
    crawler_cached = cache.get(crawler_key)

    # --- Fetch from providers (parallel, only on cache miss) ---
    google_venues: list[Venue] = google_cached or []
    crawler_venues: list[Venue] = crawler_cached or []

    tasks: list[asyncio.Task] = []
    task_labels: list[str] = []

    if google_cached is None:
        async def _fetch_google() -> list[Venue]:
            return await _get_google().fetch(
                district, interests, lat=centre_lat, lng=centre_lng,
            )
        tasks.append(asyncio.create_task(_fetch_google()))
        task_labels.append("google")

    if crawler_cached is None:
        async def _fetch_crawler() -> list[Venue]:
            return await _get_crawler().fetch(
                district, interests, lat=centre_lat, lng=centre_lng,
            )
        tasks.append(asyncio.create_task(_fetch_crawler()))
        task_labels.append("crawler")

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for label, result in zip(task_labels, results):
            if isinstance(result, Exception):
                logger.warning("Provider %s failed: %s", label, result)
                result_venues: list[Venue] = []
            else:
                result_venues = result

            # Cache even empty results to avoid re-fetching on failure
            cache_key = make_cache_key(label, district, interests)
            cache.put(cache_key, result_venues)

            if label == "google":
                google_venues = result_venues
            else:
                crawler_venues = result_venues

    # --- Normalize districts ---
    for v in google_venues:
        _assign_district(v)
    for v in crawler_venues:
        _assign_district(v)

    # --- Merge + deduplicate ---
    # Google first (usually higher data quality), crawler second
    merged = list(google_venues) + list(crawler_venues)
    merged = _deduplicate(merged)

    logger.info(
        "Aggregator: google=%d, crawler=%d, merged=%d",
        len(google_venues), len(crawler_venues), len(merged),
    )

    # --- Check if we need seed fallback ---
    used_fallback = False
    if len(merged) < 3:
        logger.info("External sources returned < 3 venues — falling back to seed data")
        seed_venues = await seed_filter_venues(
            district=district,
            indoor_pref=indoor_pref,
            cost_level=cost_level,
        )
        # Merge seed into results (external first, then seed to fill gaps)
        merged = _deduplicate(merged + seed_venues)
        used_fallback = True

    # --- Filter ---
    filtered = _basic_filter(merged, district, indoor_pref, cost_level)

    return filtered, used_fallback
