from datetime import datetime

from pydantic import BaseModel


class MentionOut(BaseModel):
    platform: str
    source_url: str | None = None
    original_text: str | None = None
    sentiment_score: float | None = None
    crowdedness: float | None = None
    vibe_tags: list[str] | None = None
    posted_at: datetime | None = None

    model_config = {"from_attributes": True}


class PlaceFeaturesOut(BaseModel):
    couple_score: float | None = None
    family_score: float | None = None
    photo_score: float | None = None
    food_score: float | None = None
    culture_score: float | None = None
    rainy_day_score: float | None = None
    crowd_score: float | None = None
    transport_score: float | None = None
    hidden_gem_score: float | None = None
    feature_json: dict | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PlaceListItem(BaseModel):
    id: int
    google_place_id: str
    display_name: str
    name_zh: str | None = None
    name_en: str | None = None
    primary_type: str | None = None
    district: str | None = None
    formatted_address: str | None = None
    rating: float | None = None
    indoor: bool | None = None
    outdoor: bool | None = None
    budget_level: str | None = None
    vibe_tags: list[str] | None = None
    mention_count: int | None = None
    sentiment_score: float | None = None
    trend_score: float | None = None

    model_config = {"from_attributes": True}


class PlaceDetail(BaseModel):
    id: int
    google_place_id: str
    display_name: str
    name_zh: str | None = None
    name_en: str | None = None
    normalized_name: str | None = None
    primary_type: str | None = None
    types_json: dict | list | None = None
    formatted_address: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    rating: float | None = None
    user_rating_count: int | None = None
    price_level: str | None = None
    business_status: str | None = None
    google_maps_uri: str | None = None
    website_uri: str | None = None
    national_phone_number: str | None = None
    opening_hours_json: dict | list | None = None
    indoor: bool | None = None
    outdoor: bool | None = None
    budget_level: str | None = None
    vibe_tags: list[str] | None = None
    mention_count: int | None = None
    sentiment_score: float | None = None
    trend_score: float | None = None
    confidence_score: float | None = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime | None = None
    features: PlaceFeaturesOut | None = None
    recent_mentions: list[MentionOut] | None = None

    model_config = {"from_attributes": True}


class GoogleImportRequest(BaseModel):
    payload: dict
    features: dict | None = None


class ImportResult(BaseModel):
    place_id: int | None = None
    google_place_id: str
    action: str
