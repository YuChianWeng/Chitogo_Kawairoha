from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.place import PlaceDetail


class InternalCategory(str, Enum):
    attraction = "attraction"
    food = "food"
    shopping = "shopping"
    lodging = "lodging"
    transport = "transport"
    nightlife = "nightlife"
    other = "other"


class PlaceSearchSort(str, Enum):
    rating_desc = "rating_desc"
    user_rating_count_desc = "user_rating_count_desc"


class NearbySort(str, Enum):
    distance_asc = "distance_asc"
    rating_desc = "rating_desc"
    user_rating_count_desc = "user_rating_count_desc"


class PlaceCandidateOut(BaseModel):
    id: int
    google_place_id: str
    display_name: str
    primary_type: str | None = None
    district: str | None = None
    formatted_address: str | None = None
    rating: float | None = None
    user_rating_count: int | None = None
    price_level: str | None = None
    budget_level: str | None = None
    internal_category: str
    latitude: float | None = None
    longitude: float | None = None
    indoor: bool | None = None
    outdoor: bool | None = None
    business_status: str | None = None
    google_maps_uri: str | None = None

    model_config = {"from_attributes": True}


class PlaceSearchResponse(BaseModel):
    items: list[PlaceCandidateOut]
    total: int
    limit: int
    offset: int


class SearchQueryParams(BaseModel):
    district: str | None = None
    internal_category: InternalCategory | None = None
    primary_type: str | None = None
    keyword: str | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_budget_level: int | None = Field(default=None, ge=0, le=4)
    indoor: bool | None = None
    open_now: bool | None = None
    sort: PlaceSearchSort = PlaceSearchSort.rating_desc
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class NearbyQueryParams(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: int = Field(gt=0)
    internal_category: InternalCategory | None = None
    primary_type: str | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_budget_level: int | None = Field(default=None, ge=0, le=4)
    limit: int = Field(default=20, ge=1, le=100)
    sort: NearbySort = NearbySort.distance_asc


class NearbyPlaceCandidateOut(PlaceCandidateOut):
    distance_m: float


class NearbyResponse(BaseModel):
    items: list[NearbyPlaceCandidateOut]
    total: int
    limit: int


class RecommendRequest(BaseModel):
    districts: list[str] | None = None
    internal_category: InternalCategory | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_budget_level: int | None = Field(default=None, ge=0, le=4)
    indoor: bool | None = None
    open_now: bool | None = None
    limit: int = Field(default=10, ge=1, le=50)


class PlaceRecommendationOut(PlaceCandidateOut):
    recommendation_score: float


class PlaceRecommendationResponse(BaseModel):
    items: list[PlaceRecommendationOut]
    total: int
    limit: int
    offset: int = 0


class BatchRequest(BaseModel):
    place_ids: list[int] = Field(min_length=1, max_length=100)


class BatchPlaceDetailOut(PlaceDetail):
    internal_category: str


class BatchResponse(BaseModel):
    items: list[BatchPlaceDetailOut]


class PlaceStatsResponse(BaseModel):
    total_places: int
    by_district: dict[str, int]
    by_internal_category: dict[str, int]
    by_primary_type: dict[str, int]


class CategoryItem(BaseModel):
    value: str
    label: str
    representative_types: list[str]


class CategoriesResponse(BaseModel):
    categories: list[CategoryItem]
