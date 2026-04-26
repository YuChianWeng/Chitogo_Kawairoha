from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.intents import Intent

InternalCategory = Literal[
    "attraction",
    "food",
    "shopping",
    "lodging",
    "transport",
    "nightlife",
    "other",
]

PlaceSort = Literal[
    "rating_desc",
    "user_rating_count_desc",
    "mention_count_desc",
    "trend_score_desc",
    "sentiment_desc",
]
NearbySort = Literal["distance_asc", "rating_desc", "user_rating_count_desc"]
RouteTransportMode = Literal["walk", "transit", "drive"]


class ToolPlace(BaseModel):
    """Normalized place shape returned by the external retrieval adapter."""

    venue_id: int | str
    name: str = Field(..., min_length=1)
    source_category: str | None = None
    category: str | None = None
    district: str | None = None
    primary_type: str | None = None
    formatted_address: str | None = None
    lat: float | None = None
    lng: float | None = None
    rating: float | None = None
    user_rating_count: int | None = None
    price_level: str | None = None
    budget_level: str | None = None
    indoor: bool | None = None
    outdoor: bool | None = None
    google_maps_uri: str | None = None
    recommendation_score: float | None = None
    distance_m: float | None = None
    vibe_tags: list[str] | None = None
    mention_count: int | None = None
    sentiment_score: float | None = None
    trend_score: float | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class PlaceListResult(BaseModel):
    """Safe list result for place queries."""

    status: Literal["ok", "empty", "error"]
    items: list[ToolPlace] = Field(default_factory=list)
    total: int = 0
    limit: int | None = None
    offset: int | None = None
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class VibeTagItem(BaseModel):
    tag: str = Field(..., min_length=1)
    place_count: int = Field(ge=0)
    mention_count: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


class VibeTagListResult(BaseModel):
    status: Literal["ok", "empty", "error"]
    items: list[VibeTagItem] = Field(default_factory=list)
    limit: int | None = None
    scope: dict[str, str | None] = Field(default_factory=dict)
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class CategoryItem(BaseModel):
    value: str
    label: str
    representative_types: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CategoryListResult(BaseModel):
    status: Literal["ok", "empty", "error"]
    categories: list[CategoryItem] = Field(default_factory=list)
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class PlaceStatsResult(BaseModel):
    status: Literal["ok", "empty", "error"]
    total_places: int = 0
    by_district: dict[str, int] = Field(default_factory=dict)
    by_internal_category: dict[str, int] = Field(default_factory=dict)
    by_primary_type: dict[str, int] = Field(default_factory=dict)
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class LodgingLegalInfo(BaseModel):
    license_no: str
    name: str
    lodging_category: str
    district: str | None = None
    address: str | None = None
    phone: str | None = None
    room_count: int | None = None
    has_hot_spring: bool
    approved_date: str | None = None
    place_id: int | None = None

    model_config = ConfigDict(extra="ignore")


class LodgingLegalCheckResult(BaseModel):
    status: Literal["ok", "error"]
    is_legal: bool = False
    lodging: LodgingLegalInfo | None = None
    # 'phone' | 'website' | 'name' | 'exact'
    match_type: str | None = None
    confidence: float | None = None
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class LegalLodgingSummary(BaseModel):
    license_no: str
    name: str
    lodging_category: str
    district: str | None = None
    address: str | None = None
    phone: str | None = None
    place_id: int | None = None

    model_config = ConfigDict(extra="ignore")


class LegalLodgingListResult(BaseModel):
    status: Literal["ok", "empty", "error"]
    items: list[LegalLodgingSummary] = Field(default_factory=list)
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class LodgingCandidateItem(BaseModel):
    license_no: str | None = None
    place_id: int | None = None
    name: str
    district: str | None = None
    address: str | None = None
    confidence: float

    model_config = ConfigDict(extra="ignore")


class LodgingCandidatesResult(BaseModel):
    status: Literal["ok", "empty", "error"]
    items: list[LodgingCandidateItem] = Field(default_factory=list)
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class RouteResult(BaseModel):
    """Structured route estimate with explicit fallback state."""

    distance_m: int = Field(ge=0)
    duration_min: int = Field(ge=0)
    provider: str
    status: Literal["ok", "fallback", "invalid_input"]
    transport_mode: RouteTransportMode = "transit"
    estimated: bool = False
    warning: str | None = None
    fallback_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolDefinition:
    """Declarative registry entry for future agent tool exposure."""

    name: str
    description: str
    handler: Any
    intents: frozenset[Intent]
