from __future__ import annotations

from app.models.db import Venue
from app.models.schemas import ScoredVenue, WeatherContext

# Scoring weights
W_INTEREST = 0.40
W_WEATHER = 0.30
W_TREND = 0.20
W_BUDGET = 0.10

# Weather suitability: condition → (indoor_score, outdoor_score)
_WEATHER_MATRIX: dict[str, tuple[float, float]] = {
    "rain": (1.0, 0.2),
    "drizzle": (0.9, 0.4),
    "cloudy": (0.7, 0.8),
    "clear": (0.5, 1.0),
    "hot": (0.9, 0.4),
    "unknown": (0.85, 0.85),
}

# Budget compatibility: (venue_cost_level, user_budget) → score
_BUDGET_COMPAT: dict[tuple[str, str], float] = {
    ("low", "low"): 1.0,
    ("low", "medium"): 1.0,
    ("low", "high"): 0.8,
    ("medium", "low"): 0.5,
    ("medium", "medium"): 1.0,
    ("medium", "high"): 1.0,
    ("high", "low"): 0.0,
    ("high", "medium"): 0.6,
    ("high", "high"): 1.0,
}


def _interest_score(venue: Venue, interests: list[str]) -> float:
    if not interests:
        return 0.5
    matched = sum(1 for tag in venue.tags if tag in interests)
    return min(1.0, matched / len(interests) + 0.1 * matched)


def _weather_score(venue: Venue, weather: WeatherContext) -> float:
    condition = weather.condition.lower()
    indoor_score, outdoor_score = _WEATHER_MATRIX.get(
        condition, _WEATHER_MATRIX["unknown"]
    )
    return indoor_score if venue.indoor else outdoor_score


def _budget_score(venue: Venue, user_budget: str) -> float:
    return _BUDGET_COMPAT.get((venue.cost_level, user_budget), 0.5)


def _build_reason(
    venue: Venue,
    interests: list[str],
    companion: str,
    weather: WeatherContext,
) -> str:
    time_of_day = "daytime"  # placeholder; routing layer refines this
    top_interest = interests[0] if interests else venue.category
    condition = weather.condition if weather.condition != "unknown" else "any weather"
    return (
        f"{venue.name} is a {venue.category} in {venue.district}, "
        f"popular with {companion} visitors and well-suited for {top_interest} "
        f"on a {condition} {time_of_day}."
    )


class ScoringEngine:
    def score(
        self,
        venues: list[Venue],
        interests: list[str],
        budget: str,
        companion: str,
        weather: WeatherContext,
    ) -> list[ScoredVenue]:
        scored: list[ScoredVenue] = []
        for v in venues:
            s_interest = _interest_score(v, interests)
            s_weather = _weather_score(v, weather)
            s_trend = v.trend_score
            s_budget = _budget_score(v, budget)

            total = (
                W_INTEREST * s_interest
                + W_WEATHER * s_weather
                + W_TREND * s_trend
                + W_BUDGET * s_budget
            )

            reason = _build_reason(v, interests, companion, weather)

            scored.append(
                ScoredVenue(
                    venue_id=v.venue_id,
                    name=v.name,
                    district=v.district,
                    category=v.category,
                    address=v.address,
                    lat=v.lat,
                    lng=v.lng,
                    indoor=v.indoor,
                    cost_level=v.cost_level,
                    avg_duration_minutes=v.avg_duration_minutes,
                    tags=v.tags,
                    score=round(total, 4),
                    reason=reason,
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored
