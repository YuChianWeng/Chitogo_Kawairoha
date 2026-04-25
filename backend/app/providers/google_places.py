"""Google Places API (New) provider for candidate venues."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.db import Venue
from app.providers.base import (
    BLOCKED_PLACE_TYPES,
    GOOGLE_TYPE_TO_CATEGORY,
    INTEREST_TO_GOOGLE_TYPE,
    district_centre,
    map_cost_level,
    stable_venue_id,
)

logger = logging.getLogger(__name__)

# Google Places Nearby Search (New) endpoint
_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
_DETAIL_FIELDS = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.types,places.priceLevel,"
    "places.rating,places.userRatingCount,places.businessStatus,"
    "places.currentOpeningHours,places.regularOpeningHours"
)
_TIMEOUT = 8.0  # seconds
_MAX_RESULTS = 20
_MIN_RATING_COUNT = 20
_MIN_RATING = 3.8


def _interests_to_included_types(interests: list[str]) -> list[str]:
    types: list[str] = []
    for interest in interests:
        gtype = INTEREST_TO_GOOGLE_TYPE.get(interest)
        if gtype and gtype not in types:
            types.append(gtype)
    if not types:
        types = ["restaurant", "cafe", "tourist_attraction"]
    return types


def _classify(google_types: list[str]) -> tuple[str, list[str], bool]:
    """Return (category, tags, indoor) from Google types."""
    category = "landmark"
    tags: list[str] = []
    indoor = True  # conservative default

    for gt in google_types:
        if gt in GOOGLE_TYPE_TO_CATEGORY:
            category = GOOGLE_TYPE_TO_CATEGORY[gt]
            break

    # Map types to interest tags
    type_tag_map = {
        "restaurant": "food",
        "cafe": "cafe",
        "museum": "culture",
        "art_gallery": "art",
        "shopping_mall": "shopping",
        "park": "nature",
        "night_club": "nightlife",
        "hindu_temple": "temple",
        "tourist_attraction": "culture",
        "bar": "nightlife",
        "bakery": "food",
    }
    for gt in google_types:
        tag = type_tag_map.get(gt)
        if tag and tag not in tags:
            tags.append(tag)

    outdoor_types = {"park", "campground", "zoo", "amusement_park", "stadium"}
    if any(t in outdoor_types for t in google_types):
        indoor = False

    if not tags:
        tags = [category]

    return category, tags[:5], indoor


def _trend_score_from_rating(rating: float | None, count: int | None) -> float:
    """Approximate trend from Google rating + count."""
    if rating is None:
        return 0.5
    base = min(rating / 5.0, 1.0)
    count_boost = min((count or 0) / 5000, 0.2)
    return round(min(base + count_boost, 1.0), 2)


def _parse_place(place: dict[str, Any]) -> Venue | None:
    """Convert a Google Places API result to an internal Venue."""
    try:
        loc = place.get("location", {})
        lat = loc.get("latitude")
        lng = loc.get("longitude")
        if lat is None or lng is None:
            return None

        name = place.get("displayName", {}).get("text", "Unknown")
        address = place.get("formattedAddress", "")
        google_types = place.get("types", [])
        price_level_str = place.get("priceLevel", "PRICE_LEVEL_UNSPECIFIED")
        rating = place.get("rating")
        user_count = place.get("userRatingCount")

        # Layer 3 — type blocklist: non-tourist venue types
        if any(t in BLOCKED_PLACE_TYPES for t in google_types):
            return None

        # Layer 2 — business status: skip closed places
        business_status = place.get("businessStatus")
        if business_status is not None and business_status != "OPERATIONAL":
            return None

        # Layer 1 — quality gate: skip low-review or low-rated places
        if user_count is not None and user_count < _MIN_RATING_COUNT:
            return None
        if rating is not None and rating < _MIN_RATING:
            return None

        # Parse price level enum string
        price_map = {
            "PRICE_LEVEL_FREE": 0,
            "PRICE_LEVEL_INEXPENSIVE": 1,
            "PRICE_LEVEL_MODERATE": 2,
            "PRICE_LEVEL_EXPENSIVE": 3,
            "PRICE_LEVEL_VERY_EXPENSIVE": 4,
        }
        price_int = price_map.get(price_level_str)

        category, tags, indoor = _classify(google_types)

        # Estimate dwell time by category
        dwell_map = {
            "restaurant": 60, "cafe": 45, "museum": 90, "gallery": 60,
            "shopping": 75, "park": 60, "nightlife": 90, "temple": 40,
            "landmark": 60, "activity": 60, "market": 60,
        }
        avg_duration = dwell_map.get(category, 60)

        return Venue(
            venue_id=stable_venue_id("google", place["id"]),
            name=name,
            district="",  # filled by aggregator based on coordinates
            category=category,
            address=address,
            lat=lat,
            lng=lng,
            indoor=indoor,
            cost_level=map_cost_level(price_int),
            avg_duration_minutes=avg_duration,
            tags=tags,
            trend_score=_trend_score_from_rating(rating, user_count),
            opening_hour=9,
            closing_hour=21,
        )
    except Exception:
        logger.debug("Failed to parse Google place: %s", place.get("id"), exc_info=True)
        return None


class GooglePlacesProvider:
    """Fetch candidate venues from Google Places API (New)."""

    async def fetch(
        self,
        district: str,
        interests: list[str],
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> list[Venue]:
        settings = get_settings()
        api_key = settings.google_places_api_key
        if not api_key:
            logger.warning("GOOGLE_PLACES_API_KEY not set — skipping Google provider")
            return []

        centre_lat, centre_lng = lat or 0, lng or 0
        if not centre_lat:
            centre_lat, centre_lng = district_centre(district)

        included_types = _interests_to_included_types(interests)

        body = {
            "includedTypes": included_types,
            "maxResultCount": _MAX_RESULTS,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": centre_lat, "longitude": centre_lng},
                    "radius": 3000.0,
                }
            },
            "languageCode": "en",
        }

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": _DETAIL_FIELDS,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(_NEARBY_URL, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.warning("Google Places API call failed", exc_info=True)
            return []

        places = data.get("places", [])
        venues: list[Venue] = []
        for p in places:
            v = _parse_place(p)
            if v is not None:
                venues.append(v)

        logger.info("Google Places returned %d venues for district=%s", len(venues), district)
        return venues
