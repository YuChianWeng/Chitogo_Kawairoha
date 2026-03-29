from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.models.db import get_all_venues
from app.models.schemas import (
    ErrorResponse,
    ItineraryResponse,
    UserPreferencesRequest,
    WeatherContext,
)
from app.services.itinerary_builder import ItineraryBuilder

router = APIRouter()
_builder = ItineraryBuilder()


@router.post(
    "/itinerary",
    response_model=ItineraryResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_itinerary(prefs: UserPreferencesRequest) -> ItineraryResponse:
    """Generate a same-day itinerary for Taipei based on user preferences."""
    # Weather integration is T030+; use neutral context for now
    weather = WeatherContext(condition="unknown")
    return await _builder.build(prefs, weather=weather)


@router.get("/venues")
async def list_venues(
    district: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> JSONResponse:
    """Debug endpoint: list seeded venues."""
    venues = await get_all_venues()
    if district:
        venues = [v for v in venues if v.district == district]
    data = [
        {
            "venue_id": v.venue_id,
            "name": v.name,
            "district": v.district,
            "category": v.category,
            "indoor": v.indoor,
            "cost_level": v.cost_level,
            "tags": v.tags,
        }
        for v in venues[:limit]
    ]
    return JSONResponse(content={"count": len(data), "venues": data})
