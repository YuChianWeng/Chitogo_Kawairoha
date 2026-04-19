from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.place import Place
from app.models.place_features import PlaceFeatures
from app.schemas.place import (
    GoogleImportRequest,
    ImportResult,
    PlaceDetail,
    PlaceFeaturesOut,
    PlaceListItem,
)
from app.schemas.retrieval import (
    BatchPlaceDetailOut,
    BatchRequest,
    BatchResponse,
    CategoriesResponse,
    CategoryItem,
    InternalCategory,
    NearbyPlaceCandidateOut,
    NearbyQueryParams,
    NearbyResponse,
    NearbySort,
    PlaceStatsResponse,
    PlaceCandidateOut,
    PlaceRecommendationOut,
    PlaceRecommendationResponse,
    PlaceSearchResponse,
    PlaceSearchSort,
    RecommendRequest,
)
from app.services.category import get_category_metadata
from app.services.ingestion import ingest_google_place
from app.services.place_nearby import MAX_NEARBY_RADIUS_M, NearbyParams, nearby_places
from app.services.place_recommendation import RecommendParams, recommend_places
from app.services.place_retrieval import batch_get_places, get_place_stats
from app.services.place_search import PlaceSearchParams, search_places

router = APIRouter()


@router.get("/places", response_model=list[PlaceListItem])
def list_places(
    district: str | None = None,
    primary_type: str | None = None,
    indoor: bool | None = None,
    budget_level: str | None = None,
    min_rating: float | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Place)

    if district is not None:
        query = query.filter(Place.district == district)
    if primary_type is not None:
        query = query.filter(Place.primary_type == primary_type)
    if indoor is not None:
        query = query.filter(Place.indoor == indoor)
    if budget_level is not None:
        query = query.filter(Place.budget_level == budget_level)
    if min_rating is not None:
        query = query.filter(Place.rating >= min_rating)

    return query.offset(offset).limit(limit).all()


@router.get("/places/search", response_model=PlaceSearchResponse)
def search_places_endpoint(
    district: str | None = None,
    internal_category: InternalCategory | None = None,
    primary_type: str | None = None,
    keyword: str | None = None,
    min_rating: float | None = Query(default=None, ge=0, le=5),
    max_budget_level: int | None = Query(default=None, ge=0, le=4),
    indoor: bool | None = None,
    open_now: bool | None = None,
    sort: PlaceSearchSort = Query(default=PlaceSearchSort.rating_desc),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    result = search_places(
        db,
        PlaceSearchParams(
            district=district,
            internal_category=(
                internal_category.value if internal_category is not None else None
            ),
            primary_type=primary_type,
            keyword=keyword,
            min_rating=min_rating,
            max_budget_level=max_budget_level,
            indoor=indoor,
            open_now=open_now,
            sort=sort,
            limit=limit,
            offset=offset,
        ),
    )
    return PlaceSearchResponse(
        items=[PlaceCandidateOut.model_validate(place) for place in result.items],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@router.get("/places/nearby", response_model=NearbyResponse)
def nearby_places_endpoint(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_m: int = Query(gt=0),
    internal_category: InternalCategory | None = None,
    primary_type: str | None = None,
    min_rating: float | None = Query(default=None, ge=0, le=5),
    max_budget_level: int | None = Query(default=None, ge=0, le=4),
    limit: int = Query(default=20, ge=1, le=100),
    sort: NearbySort = Query(default=NearbySort.distance_asc),
    db: Session = Depends(get_db),
):
    if radius_m > MAX_NEARBY_RADIUS_M:
        raise HTTPException(
            status_code=422,
            detail=f"radius_m must not exceed {MAX_NEARBY_RADIUS_M}",
        )

    result = nearby_places(
        db,
        NearbyParams(
            lat=lat,
            lng=lng,
            radius_m=radius_m,
            internal_category=(
                internal_category.value if internal_category is not None else None
            ),
            primary_type=primary_type,
            min_rating=min_rating,
            max_budget_level=max_budget_level,
            limit=limit,
            sort=sort,
        ),
    )
    return NearbyResponse(
        items=[
            NearbyPlaceCandidateOut(
                **PlaceCandidateOut.model_validate(item.place).model_dump(),
                distance_m=item.distance_m,
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
    )


@router.post("/places/recommend", response_model=PlaceRecommendationResponse)
def recommend_places_endpoint(
    request: RecommendRequest,
    db: Session = Depends(get_db),
):
    result = recommend_places(
        db,
        RecommendParams(
            districts=request.districts,
            internal_category=(
                request.internal_category.value
                if request.internal_category is not None
                else None
            ),
            min_rating=request.min_rating,
            max_budget_level=request.max_budget_level,
            indoor=request.indoor,
            open_now=request.open_now,
            limit=request.limit,
        ),
    )
    return PlaceRecommendationResponse(
        items=[
            PlaceRecommendationOut(
                **PlaceCandidateOut.model_validate(item.place).model_dump(),
                recommendation_score=item.recommendation_score,
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@router.post("/places/batch", response_model=BatchResponse)
def batch_places_endpoint(
    request: BatchRequest,
    db: Session = Depends(get_db),
):
    result = batch_get_places(db, request.place_ids)
    return BatchResponse(
        items=[
            _build_batch_place_detail(place, result.features_map.get(place.id))
            for place in result.places
        ]
    )


@router.get("/places/stats", response_model=PlaceStatsResponse)
def place_stats_endpoint(db: Session = Depends(get_db)):
    result = get_place_stats(db)
    return PlaceStatsResponse(
        total_places=result.total_places,
        by_district=result.by_district,
        by_internal_category=result.by_internal_category,
        by_primary_type=result.by_primary_type,
    )


@router.get("/places/categories", response_model=CategoriesResponse)
def place_categories_endpoint():
    return CategoriesResponse(
        categories=[
            CategoryItem.model_validate(item) for item in get_category_metadata()
        ]
    )


@router.get("/places/{place_id}", response_model=PlaceDetail)
def get_place(place_id: int, db: Session = Depends(get_db)):
    place = db.query(Place).filter(Place.id == place_id).first()
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")

    features = db.query(PlaceFeatures).filter(PlaceFeatures.place_id == place_id).first()
    detail = PlaceDetail.model_validate(place)
    if features is None:
        return detail
    return detail.model_copy(update={"features": PlaceFeaturesOut.model_validate(features)})


def _build_batch_place_detail(
    place: Place, features: PlaceFeatures | None
) -> BatchPlaceDetailOut:
    detail = BatchPlaceDetailOut.model_validate(place)
    if features is None:
        return detail
    return detail.model_copy(update={"features": PlaceFeaturesOut.model_validate(features)})


@router.post("/places/import/google", response_model=ImportResult)
def import_google_place(
    request: GoogleImportRequest, db: Session = Depends(get_db)
):
    try:
        result = ingest_google_place(db, request.payload, request.features)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result
