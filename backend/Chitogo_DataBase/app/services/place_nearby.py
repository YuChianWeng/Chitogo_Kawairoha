from __future__ import annotations

from dataclasses import dataclass
from math import acos, cos, radians, sin

from sqlalchemy.orm import Query
from sqlalchemy.orm import Session

from app.models.place import Place
from app.schemas.retrieval import NearbySort
from app.services.place_search import PlaceSearchParams, apply_place_search_filters

EARTH_RADIUS_M = 6_371_000
MAX_NEARBY_RADIUS_M = 10_000
METERS_PER_DEGREE = 111_320


@dataclass(frozen=True)
class NearbyParams:
    lat: float
    lng: float
    radius_m: int
    internal_category: str | None = None
    primary_type: str | None = None
    min_rating: float | None = None
    max_budget_level: int | None = None
    limit: int = 20
    sort: NearbySort = NearbySort.distance_asc


@dataclass(frozen=True)
class NearbyCandidate:
    place: Place
    distance_m: float


@dataclass(frozen=True)
class NearbyResult:
    items: list[NearbyCandidate]
    total: int
    limit: int


def nearby_places(db: Session, params: NearbyParams) -> NearbyResult:
    query = build_nearby_query(db, params)
    candidates = [
        NearbyCandidate(
            place=place,
            distance_m=round(
                haversine_distance_m(
                    params.lat,
                    params.lng,
                    float(place.latitude),
                    float(place.longitude),
                ),
                1,
            ),
        )
        for place in query.all()
    ]
    candidates = [
        candidate for candidate in candidates if candidate.distance_m <= params.radius_m
    ]
    sort_nearby_candidates(candidates, params.sort)

    return NearbyResult(
        items=candidates[: params.limit],
        total=len(candidates),
        limit=params.limit,
    )


def build_nearby_query(db: Session, params: NearbyParams) -> Query:
    min_lat, max_lat, min_lng, max_lng = bounding_box(
        params.lat, params.lng, params.radius_m
    )
    query = db.query(Place)
    query = query.filter(Place.latitude.is_not(None))
    query = query.filter(Place.longitude.is_not(None))
    query = query.filter(Place.latitude >= min_lat)
    query = query.filter(Place.latitude <= max_lat)
    query = query.filter(Place.longitude >= min_lng)
    query = query.filter(Place.longitude <= max_lng)
    return apply_place_search_filters(
        query,
        PlaceSearchParams(
            internal_category=params.internal_category,
            primary_type=params.primary_type,
            min_rating=params.min_rating,
            max_budget_level=params.max_budget_level,
        ),
    )


def bounding_box(lat: float, lng: float, radius_m: int) -> tuple[float, float, float, float]:
    lat_delta = radius_m / METERS_PER_DEGREE
    cos_lat = abs(cos(radians(lat)))
    if cos_lat < 1e-12:
        lng_delta = 180.0
    else:
        lng_delta = radius_m / (METERS_PER_DEGREE * cos_lat)

    min_lat = max(-90.0, lat - lat_delta)
    max_lat = min(90.0, lat + lat_delta)
    min_lng = max(-180.0, lng - lng_delta)
    max_lng = min(180.0, lng + lng_delta)
    return min_lat, max_lat, min_lng, max_lng


def haversine_distance_m(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> float:
    origin_lat_rad = radians(origin_lat)
    dest_lat_rad = radians(dest_lat)
    lng_delta_rad = radians(dest_lng - origin_lng)
    cosine = (
        cos(origin_lat_rad) * cos(dest_lat_rad) * cos(lng_delta_rad)
        + sin(origin_lat_rad) * sin(dest_lat_rad)
    )
    clamped_cosine = min(1.0, max(-1.0, cosine))
    return EARTH_RADIUS_M * acos(clamped_cosine)


def sort_nearby_candidates(
    candidates: list[NearbyCandidate], sort: NearbySort
) -> None:
    if sort == NearbySort.rating_desc:
        candidates.sort(
            key=lambda candidate: (
                candidate.place.rating is None,
                -float(candidate.place.rating)
                if candidate.place.rating is not None
                else 0.0,
                candidate.distance_m,
                candidate.place.id,
            )
        )
        return

    if sort == NearbySort.user_rating_count_desc:
        candidates.sort(
            key=lambda candidate: (
                candidate.place.user_rating_count is None,
                -(candidate.place.user_rating_count or 0),
                candidate.distance_m,
                candidate.place.id,
            )
        )
        return

    candidates.sort(key=lambda candidate: (candidate.distance_m, candidate.place.id))
