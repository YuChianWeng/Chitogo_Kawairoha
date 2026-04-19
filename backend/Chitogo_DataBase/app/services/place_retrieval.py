from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.place_features import PlaceFeatures


@dataclass(frozen=True)
class PlaceBatchResult:
    places: list[Place]
    features_map: dict[int, PlaceFeatures]


@dataclass(frozen=True)
class PlaceStatsResult:
    total_places: int
    by_district: dict[str, int]
    by_internal_category: dict[str, int]
    by_primary_type: dict[str, int]


def batch_get_places(db: Session, place_ids: list[int]) -> PlaceBatchResult:
    places = db.query(Place).filter(Place.id.in_(place_ids)).all()
    places_by_id = {place.id: place for place in places}

    features = db.query(PlaceFeatures).filter(PlaceFeatures.place_id.in_(place_ids)).all()
    features_map = {feature.place_id: feature for feature in features}

    ordered_places = [
        places_by_id[place_id] for place_id in place_ids if place_id in places_by_id
    ]
    return PlaceBatchResult(places=ordered_places, features_map=features_map)


def get_place_stats(db: Session) -> PlaceStatsResult:
    total_places = db.query(Place).count()

    district_rows = (
        db.query(Place.district, func.count(Place.id).label("count"))
        .filter(Place.district.is_not(None))
        .group_by(Place.district)
        .order_by(func.count(Place.id).desc(), Place.district.asc())
        .all()
    )
    internal_category_rows = (
        db.query(Place.internal_category, func.count(Place.id).label("count"))
        .group_by(Place.internal_category)
        .order_by(func.count(Place.id).desc(), Place.internal_category.asc())
        .all()
    )
    primary_type_rows = (
        db.query(Place.primary_type, func.count(Place.id).label("count"))
        .filter(Place.primary_type.is_not(None))
        .group_by(Place.primary_type)
        .order_by(func.count(Place.id).desc(), Place.primary_type.asc())
        .all()
    )

    return PlaceStatsResult(
        total_places=total_places,
        by_district=_rows_to_count_map(district_rows),
        by_internal_category=_rows_to_count_map(internal_category_rows),
        by_primary_type=_rows_to_count_map(primary_type_rows),
    )


def _rows_to_count_map(rows: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, count in rows:
        counts[str(key)] = int(count)
    return counts
