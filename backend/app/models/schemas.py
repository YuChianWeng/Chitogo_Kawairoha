from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

VALID_DISTRICTS = {
    "Zhongzheng", "Da'an", "Zhongshan", "Xinyi", "Wanhua",
    "Songshan", "Neihu", "Shilin", "Beitou", "Wenshan",
    "Nangang", "Datong",
}

VALID_INTERESTS = {
    "food", "culture", "shopping", "nature", "nightlife",
    "art", "history", "cafe", "sports", "temple",
}

VALID_COMPANIONS = {"solo", "couple", "family", "friends"}

VALID_BUDGETS = {"low", "medium", "high"}


class UserPreferencesRequest(BaseModel):
    district: str
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    interests: list[str]
    budget: Literal["low", "medium", "high"]
    companion: Literal["solo", "couple", "family", "friends"]
    indoor_pref: Literal["indoor", "outdoor", "both"] = "both"

    @model_validator(mode="after")
    def validate_preferences(self) -> "UserPreferencesRequest":
        # Validate district
        if self.district not in VALID_DISTRICTS:
            raise ValueError(
                f"invalid_district: '{self.district}' is not a supported Taipei district"
            )

        # Validate time format and range
        try:
            sh, sm = map(int, self.start_time.split(":"))
            eh, em = map(int, self.end_time.split(":"))
        except (ValueError, AttributeError):
            raise ValueError("invalid_time_format: use HH:MM format")

        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        duration = end_mins - start_mins

        if duration < 60:
            raise ValueError(
                "time_range_too_short: minimum time range is 60 minutes"
            )
        if duration > 720:
            raise ValueError(
                "time_range_too_long: maximum time range is 720 minutes (12 hours)"
            )

        # Validate interests
        invalid = [i for i in self.interests if i not in VALID_INTERESTS]
        if invalid:
            raise ValueError(
                f"invalid_interests: {invalid} are not supported interest tags"
            )
        if not self.interests:
            raise ValueError("interests must contain at least one entry")

        return self


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class ItineraryStopResponse(BaseModel):
    order: int
    venue_id: str
    name: str
    district: str
    category: str
    address: str
    lat: float
    lng: float
    suggested_start: str  # "HH:MM"
    suggested_end: str  # "HH:MM"
    duration_minutes: int
    travel_minutes_from_prev: int
    reason: str
    tags: list[str]
    cost_level: Literal["low", "medium", "high"]
    indoor: bool


class ItineraryResponse(BaseModel):
    status: str = "ok"
    district: str
    date: str  # ISO date
    weather_condition: str
    stops: list[ItineraryStopResponse]
    total_stops: int
    total_duration_minutes: int


class ErrorResponse(BaseModel):
    status: str = "error"
    code: str
    message: str


# ---------------------------------------------------------------------------
# Internal pipeline types (dataclasses — not exposed via API)
# ---------------------------------------------------------------------------


@dataclass
class WeatherContext:
    condition: str = "unknown"  # "clear", "rain", "cloudy", "unknown"
    temperature_c: float = 25.0
    humidity_pct: float = 60.0


@dataclass
class ScoredVenue:
    venue_id: str
    name: str
    district: str
    category: str
    address: str
    lat: float
    lng: float
    indoor: bool
    cost_level: str
    avg_duration_minutes: int
    tags: list[str] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""
