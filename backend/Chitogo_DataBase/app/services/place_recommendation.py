from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from app.services.place_search import (
    PlaceSearchParams,
    apply_place_search_filters,
    get_current_taipei_time,
    is_open_now,
)

DEFAULT_RECOMMEND_CATEGORIES = ("attraction", "food", "shopping", "lodging")
FEATURE_SCORE_FIELDS = (
    "couple_score",
    "family_score",
    "photo_score",
    "food_score",
    "culture_score",
    "rainy_day_score",
    "crowd_score",
    "transport_score",
    "hidden_gem_score",
)


@dataclass(frozen=True)
class RecommendParams:
    districts: list[str] | None = None
    internal_category: str | None = None
    min_rating: float | None = None
    max_budget_level: int | None = None
    indoor: bool | None = None
    open_now: bool | None = None
    limit: int = 10


@dataclass(frozen=True)
class RecommendedPlace:
    place: Place
    recommendation_score: float


@dataclass(frozen=True)
class RecommendResult:
    items: list[RecommendedPlace]
    total: int
    limit: int
    offset: int = 0


def recommend_places(db: Session, params: RecommendParams) -> RecommendResult:
    query = build_recommendation_query(db, params)
    places = query.all()

    if params.open_now is True:
        now = get_current_taipei_time()
        places = [
            place for place in places if is_open_now(place.opening_hours_json, now=now)
        ]

    features_map = load_place_features_map(db, [place.id for place in places])
    ranked_places = [
        RecommendedPlace(
            place=place,
            recommendation_score=compute_recommendation_score(
                place, features_map.get(place.id)
            ),
        )
        for place in places
    ]
    ranked_places.sort(
        key=lambda candidate: (
            candidate.recommendation_score,
            float(candidate.place.rating) if candidate.place.rating is not None else 0.0,
        ),
        reverse=True,
    )

    total = len(ranked_places)
    return RecommendResult(
        items=ranked_places[: params.limit],
        total=total,
        limit=params.limit,
    )


def build_recommendation_query(db: Session, params: RecommendParams):
    query = db.query(Place)
    query = apply_place_search_filters(
        query,
        PlaceSearchParams(
            min_rating=params.min_rating,
            max_budget_level=params.max_budget_level,
            indoor=params.indoor,
        ),
    )
    if params.districts is not None:
        query = query.filter(Place.district.in_(params.districts))
    if params.internal_category is not None:
        query = query.filter(Place.internal_category == params.internal_category)
    else:
        query = query.filter(Place.internal_category.in_(DEFAULT_RECOMMEND_CATEGORIES))
    return query


def load_place_features_map(
    db: Session, place_ids: list[int]
) -> dict[int, PlaceFeatures]:
    if not place_ids:
        return {}
    features = (
        db.query(PlaceFeatures)
        .filter(PlaceFeatures.place_id.in_(place_ids))
        .all()
    )
    return {feature.place_id: feature for feature in features}


def compute_recommendation_score(
    place: Place, features: PlaceFeatures | None
) -> float:
    feature_values = extract_feature_values(features)
    if feature_values:
        return float(fmean(feature_values))
    if place.rating is not None:
        return float(place.rating)
    return 0.0


def extract_feature_values(features: PlaceFeatures | None) -> list[float]:
    if features is None:
        return []
    values: list[float] = []
    for field_name in FEATURE_SCORE_FIELDS:
        value = getattr(features, field_name, None)
        if value is not None:
            values.append(float(value))
    return values
