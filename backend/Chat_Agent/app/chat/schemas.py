from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.orchestration.intents import Intent
from app.session.models import Itinerary, Preferences
from app.tools.models import ToolPlace

RoutingStatus = Literal["full", "partial_fallback", "failed"]
TraceStepStatus = Literal["success", "error", "skipped", "fallback"]
TraceFinalStatus = Literal["success", "clarification", "error"]


class ChatUserContext(BaseModel):
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lng: float | None = Field(default=None, ge=-180.0, le=180.0)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> ChatUserContext:
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must be provided together")
        return self


class ChatMessageRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=4000)
    user_context: ChatUserContext | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be empty")
        return stripped


class ChatCandidate(BaseModel):
    place_id: int | str
    name: str
    district: str | None = None
    category: str | None = None
    primary_type: str | None = None
    rating: float | None = None
    budget_level: str | None = None
    why_recommended: str | None = None

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_tool_place(cls, place: ToolPlace, *, why_recommended: str | None) -> ChatCandidate:
        return cls(
            place_id=place.venue_id,
            name=place.name,
            district=place.district,
            category=place.category,
            primary_type=place.primary_type,
            rating=place.rating,
            budget_level=place.budget_level,
            why_recommended=why_recommended,
        )


class ToolResultsSummary(BaseModel):
    tools_used: list[str] = Field(default_factory=list)
    result_status: Literal["ok", "empty", "error"] = "ok"
    candidate_count: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class LoopResult(BaseModel):
    status: Literal["ok", "empty", "error"]
    tools_used: list[str] = Field(default_factory=list)
    places: list[ToolPlace] = Field(default_factory=list)
    summary: str | None = None
    error: str | None = None
    relaxations_applied: list[str] = Field(default_factory=list)
    original_filters: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ChatMessageResponse(BaseModel):
    session_id: str
    turn_id: str
    intent: Intent
    needs_clarification: bool
    message: str
    preferences: Preferences
    itinerary: Itinerary | None = None
    routing_status: RoutingStatus | None = None
    candidates: list[ChatCandidate] = Field(default_factory=list)
    tool_results_summary: ToolResultsSummary | None = None
    source: str | None = None

    model_config = ConfigDict(extra="forbid")


class ErrorEnvelope(BaseModel):
    error: str
    detail: str | None = None

    model_config = ConfigDict(extra="forbid")


class TraceStepRecord(BaseModel):
    name: str = Field(..., min_length=1)
    status: TraceStepStatus
    duration_ms: int = Field(default=0, ge=0)
    summary: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    warning: str | None = None
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class ChatTraceDetail(BaseModel):
    trace_id: str = Field(..., min_length=1)
    session_id: str | None = None
    requested_at: datetime
    intent: str | None = None
    needs_clarification: bool | None = None
    final_status: TraceFinalStatus
    outcome: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    steps: list[TraceStepRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_summary: str | None = None

    model_config = ConfigDict(extra="forbid")


class ChatTraceSummary(BaseModel):
    trace_id: str = Field(..., min_length=1)
    session_id: str | None = None
    requested_at: datetime
    intent: str | None = None
    needs_clarification: bool | None = None
    final_status: TraceFinalStatus
    outcome: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    step_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_summary: str | None = None

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_trace(cls, trace: ChatTraceDetail) -> ChatTraceSummary:
        return cls(
            trace_id=trace.trace_id,
            session_id=trace.session_id,
            requested_at=trace.requested_at,
            intent=trace.intent,
            needs_clarification=trace.needs_clarification,
            final_status=trace.final_status,
            outcome=trace.outcome,
            duration_ms=trace.duration_ms,
            step_count=len(trace.steps),
            warning_count=len(trace.warnings),
            error_summary=trace.error_summary,
        )


class ChatTraceListResponse(BaseModel):
    items: list[ChatTraceSummary] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
