from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.weather import get_weather_context

router = APIRouter(tags=["weather"])


class WeatherResponse(BaseModel):
    is_raining_likely: bool
    rain_probability: int | None
    condition: str | None = None
    temperature: int | None = None
    wind_direction: str | None = None


@router.get("/weather")
async def get_weather() -> WeatherResponse:
    ctx = await get_weather_context()
    return WeatherResponse(
        is_raining_likely=ctx.is_raining_likely,
        rain_probability=ctx.rain_probability,
        condition=ctx.condition,
        temperature=ctx.temperature,
        wind_direction=ctx.wind_direction,
    )
