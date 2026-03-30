"""Crawler / social-source provider for trending venue candidates.

This provider fetches from a configurable crawler API endpoint that returns
trending venues. The expected response format is:

{
  "venues": [
    {
      "id": "...",
      "name": "Shilin Night Market",
      "address": "...",
      "lat": 25.0882,
      "lng": 121.5240,
      "category": "market",
      "tags": ["food", "nightlife", "shopping"],
      "indoor": false,
      "price_level": 1,
      "popularity_score": 0.92,
      "avg_duration_minutes": 90
    }
  ]
}

If CRAWLER_API_URL is not set, this provider returns an empty list.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.db import Venue
from app.providers.base import map_cost_level, stable_venue_id

logger = logging.getLogger(__name__)

_TIMEOUT = 8.0


def _parse_crawler_venue(raw: dict[str, Any]) -> Venue | None:
    try:
        lat = raw.get("lat")
        lng = raw.get("lng")
        if lat is None or lng is None:
            return None

        return Venue(
            venue_id=stable_venue_id("crawler", str(raw["id"])),
            name=raw["name"],
            district="",  # filled by aggregator
            category=raw.get("category", "landmark"),
            address=raw.get("address", ""),
            lat=lat,
            lng=lng,
            indoor=raw.get("indoor", True),
            cost_level=map_cost_level(raw.get("price_level")),
            avg_duration_minutes=raw.get("avg_duration_minutes", 60),
            tags=raw.get("tags", [])[:5],
            trend_score=min(raw.get("popularity_score", 0.5), 1.0),
            opening_hour=raw.get("opening_hour", 9),
            closing_hour=raw.get("closing_hour", 21),
        )
    except Exception:
        logger.debug("Failed to parse crawler venue", exc_info=True)
        return None


class CrawlerProvider:
    """Fetch trending venues from an external crawler/social API."""

    async def fetch(
        self,
        district: str,
        interests: list[str],
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> list[Venue]:
        settings = get_settings()
        base_url = settings.crawler_api_url
        if not base_url:
            logger.info("CRAWLER_API_URL not set — skipping crawler provider")
            return []

        params: dict[str, str] = {"district": district}
        if interests:
            params["interests"] = ",".join(interests)
        if lat is not None:
            params["lat"] = str(lat)
        if lng is not None:
            params["lng"] = str(lng)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.warning("Crawler API call failed", exc_info=True)
            return []

        raw_venues = data.get("venues", [])
        venues: list[Venue] = []
        for rv in raw_venues:
            v = _parse_crawler_venue(rv)
            if v is not None:
                venues.append(v)

        logger.info("Crawler returned %d venues for district=%s", len(venues), district)
        return venues
