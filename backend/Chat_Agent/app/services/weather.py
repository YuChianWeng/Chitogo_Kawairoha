from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CWA_BASE_URL = "https://opendata.cwa.gov.tw"
_CWA_FORECAST_PATH = "/api/v1/rest/datastore/F-D0047-061"
_RAIN_THRESHOLD_PCT = 40
_CACHE_TTL_MINUTES = 30


@dataclass(frozen=True)
class WeatherContext:
    is_raining_likely: bool
    rain_probability: int | None


_cached_context: WeatherContext | None = None
_cache_expires_at: datetime = datetime.min.replace(tzinfo=UTC)


def _get_from_cache() -> WeatherContext | None:
    if _cached_context is not None and datetime.now(UTC) < _cache_expires_at:
        return _cached_context
    return None


def _set_cache(ctx: WeatherContext) -> None:
    global _cached_context, _cache_expires_at
    _cached_context = ctx
    _cache_expires_at = datetime.now(UTC) + timedelta(minutes=_CACHE_TTL_MINUTES)


def _no_rain() -> WeatherContext:
    return WeatherContext(is_raining_likely=False, rain_probability=None)


def _parse_max_pop(payload: Any) -> int | None:
    """Extract the maximum PoP12h value across all Taipei districts for the nearest time slot."""
    try:
        records = payload.get("records", {})
        locations_wrapper = records.get("Locations", [])
        if not locations_wrapper:
            return None

        location_list = locations_wrapper[0].get("Location", [])
        if not location_list:
            return None

        max_pop: int | None = None

        for location in location_list:
            for element in location.get("WeatherElement", []):
                if element.get("ElementName") != "PoP12h":
                    continue

                time_values = element.get("Time", [])
                if not time_values:
                    continue

                # Take the first (nearest) time slot value
                first_value_set = time_values[0].get("ElementValue", [])
                for ev in first_value_set:
                    raw = ev.get("PoP12h") or ev.get("Value")
                    if raw is None:
                        continue
                    try:
                        pct = int(str(raw).replace("%", "").strip())
                        if max_pop is None or pct > max_pop:
                            max_pop = pct
                    except (ValueError, TypeError):
                        continue

        return max_pop

    except Exception as exc:
        logger.warning("weather._parse_max_pop failed: %s", exc)
        return None


async def get_weather_context() -> WeatherContext:
    """Return current weather context for Taipei, using a 30-minute in-process cache.

    Fetches PoP12h (12-hour precipitation probability) from the CWA open data API.
    Returns a no-rain context on any error so candidate picking continues unaffected.
    """
    cached = _get_from_cache()
    if cached is not None:
        return cached

    from app.core.config import get_settings

    settings = get_settings()
    api_key = settings.cwa_api_key
    if not api_key:
        logger.debug("CWA_API_KEY not set; skipping weather check")
        return _no_rain()

    try:
        async with httpx.AsyncClient(
            base_url=_CWA_BASE_URL,
            timeout=settings.cwa_weather_timeout_sec,
        ) as client:
            response = await client.get(
                _CWA_FORECAST_PATH,
                params={
                    "Authorization": api_key,
                    "locationName": "台北市",
                    "elementName": "PoP12h",
                },
            )
            if response.status_code != 200:
                logger.warning(
                    "CWA weather API returned HTTP %s; skipping weather filter",
                    response.status_code,
                )
                return _no_rain()

            data = response.json()
    except httpx.TimeoutException:
        logger.warning("CWA weather API timed out; skipping weather filter")
        return _no_rain()
    except Exception as exc:
        logger.warning("CWA weather API error: %s; skipping weather filter", exc)
        return _no_rain()

    max_pop = _parse_max_pop(data)
    if max_pop is None:
        logger.warning("CWA weather API: could not parse PoP12h; skipping weather filter")
        ctx = _no_rain()
    else:
        ctx = WeatherContext(
            is_raining_likely=max_pop >= _RAIN_THRESHOLD_PCT,
            rain_probability=max_pop,
        )
        logger.info(
            "Weather context: PoP12h=%d%% → is_raining_likely=%s",
            max_pop,
            ctx.is_raining_likely,
        )

    _set_cache(ctx)
    return ctx
