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
    condition: str | None = None
    temperature: int | None = None
    wind_direction: str | None = None


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
    return WeatherContext(
        is_raining_likely=False,
        rain_probability=None,
        condition=None,
        temperature=None,
        wind_direction=None,
    )


def _parse_weather_elements(payload: Any) -> dict[str, Any]:
    """Extract Wx, T, PoP12h, and WD values across Taipei districts for the nearest time slot."""
    try:
        records = payload.get("records", {})
        locations_wrapper = records.get("Locations", [])
        if not locations_wrapper:
            return {}

        location_list = locations_wrapper[0].get("Location", [])
        if not location_list:
            return {}

        # We take the first district's first time slot as representative for Taipei
        # or we could average/max them. For now, let's take the first one found.
        first_location = location_list[0]
        elements = {}

        for element in first_location.get("WeatherElement", []):
            name = element.get("ElementName")
            time_values = element.get("Time", [])
            if not time_values:
                continue

            # Take the first (nearest) time slot value
            first_value_set = time_values[0].get("ElementValue", [])
            if not first_value_set:
                continue

            val_obj = first_value_set[0]
            if name == "PoP12h":
                raw = val_obj.get("PoP12h") or val_obj.get("Value")
                if raw is not None:
                    elements["rain_probability"] = int(str(raw).replace("%", "").strip())
            elif name == "Wx":
                elements["condition"] = val_obj.get("Wx") or val_obj.get("Value")
            elif name == "T":
                raw = val_obj.get("T") or val_obj.get("Value")
                if raw is not None:
                    elements["temperature"] = int(str(raw))
            elif name == "WD":
                elements["wind_direction"] = val_obj.get("WD") or val_obj.get("Value")

        return elements

    except Exception as exc:
        logger.warning("weather._parse_weather_elements failed: %s", exc)
        return {}


async def get_weather_context() -> WeatherContext:
    """Return current weather context for Taipei, using a 30-minute in-process cache.

    Fetches weather elements from the CWA open data API.
    Returns a default context on any error so candidate picking continues unaffected.
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
                    "elementName": "PoP12h,Wx,T,WD",
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

    elements = _parse_weather_elements(data)
    if not elements:
        logger.warning("CWA weather API: could not parse elements; skipping weather filter")
        ctx = _no_rain()
    else:
        rain_prob = elements.get("rain_probability")
        ctx = WeatherContext(
            is_raining_likely=rain_prob is not None and rain_prob >= _RAIN_THRESHOLD_PCT,
            rain_probability=rain_prob,
            condition=elements.get("condition"),
            temperature=elements.get("temperature"),
            wind_direction=elements.get("wind_direction"),
        )
        logger.info(
            "Weather context: condition=%s, temp=%s, wind=%s, PoP12h=%s",
            ctx.condition,
            ctx.temperature,
            ctx.wind_direction,
            ctx.rain_probability,
        )

    _set_cache(ctx)
    return ctx
