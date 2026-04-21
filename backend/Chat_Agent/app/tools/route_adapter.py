from __future__ import annotations

import math
from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings, get_settings
from app.tools.models import RouteResult, RouteTransportMode

_GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
_MODE_TO_GOOGLE = {
    "walk": "walking",
    "transit": "transit",
    "drive": "driving",
}
_FALLBACK_SPEED_KPH = {
    "walk": 4.5,
    "transit": 12.0,
    "drive": 30.0,
}


class RouteEstimateInput(BaseModel):
    origin_lat: float = Field(ge=-90, le=90)
    origin_lng: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lng: float = Field(ge=-180, le=180)
    transport_mode: str = "transit"
    depart_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


def haversine_distance_m(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
) -> int:
    radius_m = 6_371_000.0
    lat1 = math.radians(origin_lat)
    lat2 = math.radians(destination_lat)
    delta_lat = math.radians(destination_lat - origin_lat)
    delta_lng = math.radians(destination_lng - origin_lng)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(round(radius_m * c))


def normalize_transport_mode(value: str | None) -> RouteTransportMode:
    normalized = (value or "transit").strip().lower()
    if normalized in {"walk", "walking"}:
        return "walk"
    if normalized in {"drive", "driving", "car", "taxi", "uber"}:
        return "drive"
    return "transit"


class RouteToolAdapter:
    """Travel-time adapter with Google Maps primary routing and silent fallback."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def estimate_route(
        self,
        origin_lat: float,
        origin_lng: float,
        destination_lat: float,
        destination_lng: float,
        *,
        transport_mode: str = "transit",
        depart_at: datetime | None = None,
    ) -> RouteResult:
        normalized_mode = normalize_transport_mode(transport_mode)
        try:
            params = RouteEstimateInput(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                destination_lat=destination_lat,
                destination_lng=destination_lng,
                transport_mode=normalized_mode,
                depart_at=depart_at,
            )
        except ValidationError:
            return RouteResult(
                distance_m=0,
                duration_min=0,
                provider="validation",
                status="invalid_input",
                transport_mode=normalized_mode,
                estimated=True,
                warning="invalid_coordinates",
                fallback_reason="invalid_coordinates",
            )

        if self.settings.route_provider == "fallback":
            return self._fallback_result(
                params,
                reason="route_provider_fallback",
                warning="using_distance_estimate",
            )

        provider_result = await self._estimate_with_google_maps(params)
        if provider_result is not None:
            return provider_result
        return self._fallback_result(
            params,
            reason="provider_unavailable",
            warning="using_distance_estimate",
        )

    async def _estimate_with_google_maps(
        self,
        params: RouteEstimateInput,
    ) -> RouteResult | None:
        google_mode = _MODE_TO_GOOGLE[normalize_transport_mode(params.transport_mode)]
        request_params = {
            "origin": f"{params.origin_lat},{params.origin_lng}",
            "destination": f"{params.destination_lat},{params.destination_lng}",
            "mode": google_mode,
            "key": self.settings.google_maps_api_key,
        }
        if google_mode == "transit":
            request_params["departure_time"] = (
                str(int(params.depart_at.timestamp())) if params.depart_at else "now"
            )

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.route_service_timeout_sec,
                transport=self._transport,
            ) as client:
                response = await client.get(_GOOGLE_DIRECTIONS_URL, params=request_params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if not isinstance(payload, dict) or payload.get("status") != "OK":
            return None
        try:
            leg = payload["routes"][0]["legs"][0]
            distance_m = int(leg["distance"]["value"])
            duration_min = max(1, math.ceil(int(leg["duration"]["value"]) / 60))
        except (KeyError, IndexError, TypeError, ValueError):
            return None

        return RouteResult(
            distance_m=distance_m,
            duration_min=duration_min,
            provider="google_maps",
            status="ok",
            transport_mode=normalize_transport_mode(params.transport_mode),
            estimated=False,
        )

    def _fallback_result(
        self,
        params: RouteEstimateInput,
        *,
        reason: str,
        warning: str,
    ) -> RouteResult:
        transport_mode = normalize_transport_mode(params.transport_mode)
        distance_m = haversine_distance_m(
            params.origin_lat,
            params.origin_lng,
            params.destination_lat,
            params.destination_lng,
        )
        speed_kph = _FALLBACK_SPEED_KPH[transport_mode]
        duration_hours = 0 if distance_m == 0 else (distance_m / 1000) / speed_kph
        duration_min = max(1, math.ceil(duration_hours * 60)) if distance_m > 0 else 0
        return RouteResult(
            distance_m=distance_m,
            duration_min=duration_min,
            provider="haversine",
            status="fallback",
            transport_mode=transport_mode,
            estimated=True,
            warning=warning,
            fallback_reason=reason,
        )


route_tool_adapter = RouteToolAdapter()

__all__ = [
    "RouteToolAdapter",
    "RouteEstimateInput",
    "haversine_distance_m",
    "normalize_transport_mode",
    "route_tool_adapter",
]
