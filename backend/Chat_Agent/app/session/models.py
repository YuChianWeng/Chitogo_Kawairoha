from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class TimeWindow(BaseModel):
    """Optional user time constraints for a planning window."""

    start_time: str | None = None
    end_time: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _TIME_PATTERN.fullmatch(value):
            raise ValueError("time values must use HH:MM format")
        return value


class Preferences(BaseModel):
    """Normalized session-level user preferences."""

    companions: str | None = None
    budget_level: str | None = None
    transport_mode: str | None = None
    indoor_preference: bool | None = None
    origin: str | None = None
    district: str | None = None
    time_window: TimeWindow | None = None
    interest_tags: list[str] = Field(default_factory=list)
    avoid_tags: list[str] = Field(default_factory=list)
    language: str | None = None

    model_config = ConfigDict(extra="forbid")


class Turn(BaseModel):
    """A single user or assistant chat turn stored in session state."""

    turn_id: str = Field(..., min_length=1)
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(extra="forbid")


class Stop(BaseModel):
    """One independently addressable itinerary stop."""

    stop_index: int = Field(..., ge=0)
    venue_id: int | str | None = None
    venue_name: str = Field(..., min_length=1)
    category: str | None = None
    arrival_time: str | None = None
    visit_duration_min: int | None = Field(default=None, ge=0)
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lng: float | None = Field(default=None, ge=-180.0, le=180.0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("arrival_time")
    @classmethod
    def validate_arrival_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _TIME_PATTERN.fullmatch(value):
            raise ValueError("arrival_time must use HH:MM format")
        return value


class Leg(BaseModel):
    """A transit leg between two adjacent stops."""

    from_stop: int = Field(..., ge=0)
    to_stop: int = Field(..., ge=0)
    transit_method: str = Field(..., min_length=1)
    duration_min: int = Field(..., ge=0)
    estimated: bool = False

    model_config = ConfigDict(extra="forbid")


class Itinerary(BaseModel):
    """Structured itinerary payload stored on the session."""

    summary: str | None = None
    total_duration_min: int | None = Field(default=None, ge=0)
    stops: list[Stop] = Field(default_factory=list)
    legs: list[Leg] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_route_shape(self) -> Itinerary:
        if not self.stops:
            raise ValueError("itinerary must contain at least one stop")

        expected_indexes = list(range(len(self.stops)))
        actual_indexes = [stop.stop_index for stop in self.stops]
        if actual_indexes != expected_indexes:
            raise ValueError("stop_index values must be dense and start at 0")

        expected_leg_count = len(self.stops) - 1
        if len(self.legs) != expected_leg_count:
            raise ValueError("legs must contain exactly one entry per adjacent stop pair")

        max_index = len(self.stops) - 1
        for leg in self.legs:
            if leg.from_stop < 0 or leg.to_stop > max_index:
                raise ValueError("leg references an out-of-range stop index")
            if leg.to_stop != leg.from_stop + 1:
                raise ValueError("leg endpoints must connect adjacent stop indexes")

        if self.total_duration_min is not None:
            expected_total = sum(stop.visit_duration_min or 0 for stop in self.stops) + sum(
                leg.duration_min for leg in self.legs
            )
            if self.total_duration_min != expected_total:
                raise ValueError("total_duration_min does not match stop and leg durations")

        return self


class Place(BaseModel):
    """Cached place candidate returned by the Data Service."""

    place_id: int | str | None = None
    venue_id: int | str | None = None
    name: str = Field(..., min_length=1)
    category: str | None = None
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lng: float | None = Field(default=None, ge=-180.0, le=180.0)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_place_identifier(self) -> Place:
        if self.place_id is None and self.venue_id is None:
            raise ValueError("place_id or venue_id is required")
        return self


class ToolCallRecord(BaseModel):
    """Trace data for one tool invocation."""

    name: str = Field(..., min_length=1)
    input: Any = None
    output: Any = None
    latency_ms: int = Field(..., ge=0)

    model_config = ConfigDict(extra="forbid")


class TraceEntry(BaseModel):
    """Per-turn execution trace stored with the session."""

    turn_id: str = Field(..., min_length=1)
    intent_classified: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    composer_output: dict[str, Any] | str | None = None
    total_latency_ms: int | None = Field(default=None, ge=0)
    fallback_used: bool = False
    final_status: str | None = None

    model_config = ConfigDict(extra="forbid")


class Session(BaseModel):
    """In-memory session state for a single client-managed session id."""

    session_id: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_activity_at: datetime = Field(default_factory=utc_now)
    turns: list[Turn] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    latest_itinerary: Itinerary | None = None
    cached_candidates: list[Place] = Field(default_factory=list)
    traces: list[TraceEntry] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
