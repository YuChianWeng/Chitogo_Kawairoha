from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.orchestration.intents import Intent
from app.session.models import Preferences
from app.tools.models import ToolPlace


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

    model_config = ConfigDict(extra="forbid")


class ChatMessageResponse(BaseModel):
    session_id: str
    turn_id: str
    intent: Intent
    needs_clarification: bool
    message: str
    preferences: Preferences
    candidates: list[ChatCandidate] = Field(default_factory=list)
    tool_results_summary: ToolResultsSummary | None = None
    source: str | None = None

    model_config = ConfigDict(extra="forbid")


class ErrorEnvelope(BaseModel):
    error: str
    detail: str | None = None

    model_config = ConfigDict(extra="forbid")
