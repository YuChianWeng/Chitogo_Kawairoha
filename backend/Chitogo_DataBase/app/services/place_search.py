from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Query
from sqlalchemy.orm import Session

from app.models.place import Place
from app.schemas.retrieval import PlaceSearchSort
from app.services.category import BUDGET_RANK

TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY


@dataclass(frozen=True)
class PlaceSearchParams:
    district: str | None = None
    internal_category: str | None = None
    primary_type: str | None = None
    keyword: str | None = None
    min_rating: float | None = None
    max_budget_level: int | None = None
    indoor: bool | None = None
    open_now: bool | None = None
    sort: PlaceSearchSort = PlaceSearchSort.rating_desc
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True)
class PlaceSearchResult:
    items: list[Place]
    total: int
    limit: int
    offset: int


def get_current_taipei_time() -> datetime:
    return datetime.now(TAIPEI_TIMEZONE)


def search_places(db: Session, params: PlaceSearchParams) -> PlaceSearchResult:
    query = build_place_search_query(db, params)

    if params.open_now is True:
        now = get_current_taipei_time()
        filtered_places = [
            place for place in query.all() if is_open_now(place.opening_hours_json, now=now)
        ]
        total = len(filtered_places)
        paginated_places = filtered_places[params.offset : params.offset + params.limit]
    else:
        total = query.count()
        paginated_places = query.offset(params.offset).limit(params.limit).all()

    return PlaceSearchResult(
        items=paginated_places,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


def build_place_search_query(db: Session, params: PlaceSearchParams) -> Query:
    query = db.query(Place)
    query = apply_place_search_filters(query, params)
    return apply_place_search_sort(query, params.sort)


def apply_place_search_filters(query: Query, params: PlaceSearchParams) -> Query:
    if params.district is not None:
        query = query.filter(Place.district == params.district)
    if params.internal_category is not None:
        query = query.filter(Place.internal_category == params.internal_category)
    if params.primary_type is not None:
        query = query.filter(Place.primary_type == params.primary_type)
    if params.keyword is not None:
        query = query.filter(Place.display_name.ilike(f"%{params.keyword}%"))
    if params.min_rating is not None:
        query = query.filter(Place.rating.is_not(None))
        query = query.filter(Place.rating >= params.min_rating)
    if params.max_budget_level is not None:
        query = query.filter(Place.budget_level.is_not(None))
        query = query.filter(
            Place.budget_level.in_(_allowed_budget_levels(params.max_budget_level))
        )
    if params.indoor is not None:
        query = query.filter(Place.indoor == params.indoor)
    return query


def apply_place_search_sort(query: Query, sort: PlaceSearchSort) -> Query:
    if sort == PlaceSearchSort.user_rating_count_desc:
        return query.order_by(Place.user_rating_count.desc().nullslast())
    return query.order_by(Place.rating.desc().nullslast())


def _allowed_budget_levels(max_budget_level: int) -> list[str]:
    return [
        budget_level
        for budget_level, rank in BUDGET_RANK.items()
        if rank <= max_budget_level
    ]


def is_open_now(opening_hours_json: dict | list | None, now: datetime | None = None) -> bool:
    if not isinstance(opening_hours_json, dict):
        return False

    periods = opening_hours_json.get("periods")
    if not isinstance(periods, list) or not periods:
        return False

    current_time = now or get_current_taipei_time()
    current_minutes = _google_week_minutes(current_time)
    current_minutes_with_wrap = current_minutes + MINUTES_PER_WEEK

    for period in periods:
        if not isinstance(period, dict):
            continue

        open_minutes = _period_point_to_minutes(period.get("open"))
        close_minutes = _period_point_to_minutes(period.get("close"))
        if open_minutes is None or close_minutes is None:
            continue

        if close_minutes <= open_minutes:
            close_minutes += MINUTES_PER_WEEK

        if open_minutes <= current_minutes < close_minutes:
            return True
        if open_minutes <= current_minutes_with_wrap < close_minutes:
            return True

    return False


def _google_week_minutes(current_time: datetime) -> int:
    google_day = (current_time.weekday() + 1) % 7
    return google_day * MINUTES_PER_DAY + current_time.hour * 60 + current_time.minute


def _period_point_to_minutes(point: object) -> int | None:
    if not isinstance(point, dict):
        return None

    day = point.get("day")
    hour = point.get("hour")
    minute = point.get("minute", 0)
    if not all(isinstance(value, int) for value in (day, hour, minute)):
        return None
    if day < 0 or day > 6 or hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None

    return day * MINUTES_PER_DAY + hour * 60 + minute
