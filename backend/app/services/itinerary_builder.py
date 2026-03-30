from __future__ import annotations

from datetime import date

from app.models.schemas import (
    ItineraryResponse,
    ItineraryStopResponse,
    UserPreferencesRequest,
    WeatherContext,
)
from app.providers.aggregator import fetch_candidates
from app.services.routing import RouteOptimizer
from app.services.scoring import ScoringEngine


class ItineraryBuilder:
    def __init__(self) -> None:
        self._scorer = ScoringEngine()
        self._router = RouteOptimizer()

    async def build(
        self,
        prefs: UserPreferencesRequest,
        weather: WeatherContext | None = None,
    ) -> ItineraryResponse:
        if weather is None:
            weather = WeatherContext()  # neutral fallback

        # 1. Fetch candidate venues (dynamic external sources + seed fallback)
        venues, used_fallback = await fetch_candidates(
            district=prefs.district,
            interests=prefs.interests,
            indoor_pref=prefs.indoor_pref,
        )

        # 2. Score candidates
        scored = self._scorer.score(
            venues,
            interests=prefs.interests,
            budget=prefs.budget,
            companion=prefs.companion,
            weather=weather,
        )

        # 3. Build route
        route = self._router.build_route(
            scored_venues=scored,
            start_time=prefs.start_time,
            end_time=prefs.end_time,
        )

        if not route:
            raise ValueError(
                "no_venues_found: no suitable venues found for the given preferences"
            )

        # 4. Assemble response
        stops = [
            ItineraryStopResponse(
                order=stop.order,
                venue_id=stop.venue.venue_id,
                name=stop.venue.name,
                district=stop.venue.district,
                category=stop.venue.category,
                address=stop.venue.address,
                lat=stop.venue.lat,
                lng=stop.venue.lng,
                suggested_start=stop.suggested_start,
                suggested_end=stop.suggested_end,
                duration_minutes=stop.duration_minutes,
                travel_minutes_from_prev=stop.travel_minutes_from_prev,
                reason=stop.venue.reason,
                tags=stop.venue.tags,
                cost_level=stop.venue.cost_level,  # type: ignore[arg-type]
                indoor=stop.venue.indoor,
            )
            for stop in route
        ]

        total_duration = sum(s.duration_minutes + s.travel_minutes_from_prev for s in stops)

        return ItineraryResponse(
            status="ok",
            district=prefs.district,
            date=date.today().isoformat(),
            weather_condition=weather.condition,
            stops=stops,
            total_stops=len(stops),
            total_duration_minutes=total_duration,
        )
