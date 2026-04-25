from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_FALLBACK_SPEED_KPH = {
    "walk": 4.5,
    "transit": 12.0,
    "drive": 30.0,
}
_GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
_MODE_TO_GOOGLE = {"walk": "walking", "transit": "transit", "drive": "driving"}


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in km between two coordinates."""
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_pre_filter(
    venues: list[Any],
    origin_lat: float,
    origin_lng: float,
    max_minutes: int,
    mode: str,
) -> list[Any]:
    """Return venues within 1.5x the walking-equivalent radius."""
    speed_kph = _FALLBACK_SPEED_KPH.get("walk", 4.5)
    max_km = speed_kph * (max_minutes / 60.0) * 1.5
    result = []
    for v in venues:
        vlat = getattr(v, "lat", None)
        vlng = getattr(v, "lng", None)
        if vlat is None or vlng is None:
            continue
        dist = haversine_distance(origin_lat, origin_lng, vlat, vlng)
        if dist <= max_km:
            result.append(v)
    return result


async def route_time_estimate(
    venue: Any,
    origin_lat: float,
    origin_lng: float,
    mode: str,
    semaphore: asyncio.Semaphore,
) -> int:
    """Return estimated travel time in minutes. Falls back to haversine when configured."""
    settings = get_settings()
    if settings.route_provider == "fallback":
        return _haversine_minutes(venue, origin_lat, origin_lng, mode)

    async with semaphore:
        try:
            dest_lat = getattr(venue, "lat", None)
            dest_lng = getattr(venue, "lng", None)
            if dest_lat is None or dest_lng is None:
                return _haversine_minutes(venue, origin_lat, origin_lng, mode)

            google_mode = _MODE_TO_GOOGLE.get(mode, "transit")
            params = {
                "origin": f"{origin_lat},{origin_lng}",
                "destination": f"{dest_lat},{dest_lng}",
                "mode": google_mode,
                "key": settings.google_maps_api_key,
            }
            async with httpx.AsyncClient(timeout=settings.route_service_timeout_sec) as client:
                resp = await client.get(_GOOGLE_DIRECTIONS_URL, params=params)
                data = resp.json()

            routes = data.get("routes", [])
            if not routes:
                return _haversine_minutes(venue, origin_lat, origin_lng, mode)
            leg = routes[0]["legs"][0]
            return int(leg["duration"]["value"] / 60)
        except Exception:
            return _haversine_minutes(venue, origin_lat, origin_lng, mode)


def _haversine_minutes(venue: Any, origin_lat: float, origin_lng: float, mode: str) -> int:
    vlat = getattr(venue, "lat", None)
    vlng = getattr(venue, "lng", None)
    if vlat is None or vlng is None:
        return 30
    dist_km = haversine_distance(origin_lat, origin_lng, vlat, vlng)
    speed_kph = _FALLBACK_SPEED_KPH.get(mode, 4.5)
    return max(1, int(dist_km / speed_kph * 60))


async def graduated_fallback(
    venues: list[Any],
    origin_lat: float,
    origin_lng: float,
    max_minutes: int,
    modes: list[str],
) -> tuple[list[Any], str | None]:
    """Try to find enough reachable venues, extending limits if needed."""
    primary_mode = modes[0] if modes else "transit"
    semaphore = asyncio.Semaphore(5)

    filtered = haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes, primary_mode)
    if len(filtered) >= 6:
        return filtered, None

    # Extend by +10 minutes
    extended = haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes + 10, primary_mode)
    if len(extended) >= 6:
        return extended, f"extended search radius by 10 min (from {max_minutes} to {max_minutes + 10} min)"

    # Add transit if not included
    if "transit" not in modes:
        transit_filtered = haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes + 10, "transit")
        if len(transit_filtered) >= 6:
            return transit_filtered, "extended search and added transit mode"

    # Return best available with partial flag
    best = haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes + 20, primary_mode)
    reason = f"partial results: only {len(best)} venues within extended range"
    return best, reason
