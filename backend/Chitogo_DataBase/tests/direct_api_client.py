from __future__ import annotations

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from app.routers.places import (
    batch_places_endpoint,
    get_place,
    list_places,
    nearby_places_endpoint,
    place_categories_endpoint,
    place_stats_endpoint,
    recommend_places_endpoint,
    search_places_endpoint,
)
from app.schemas.place import PlaceDetail, PlaceListItem
from app.schemas.retrieval import BatchRequest, NearbyQueryParams, RecommendRequest
from app.schemas.retrieval import SearchQueryParams


class DirectResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = jsonable_encoder(payload)

    def json(self):
        return self._payload


class DirectApiClient:
    def __init__(self, session):
        self.session = session

    def get(self, path: str, params: dict | None = None) -> DirectResponse:
        params = params or {}

        try:
            if path == "/api/v1/places":
                payload = [
                    PlaceListItem.model_validate(item)
                    for item in list_places(
                    district=params.get("district"),
                    primary_type=params.get("primary_type"),
                    indoor=params.get("indoor"),
                    budget_level=params.get("budget_level"),
                    min_rating=params.get("min_rating"),
                    limit=params.get("limit", 50),
                    offset=params.get("offset", 0),
                    db=self.session,
                    )
                ]
            elif path == "/api/v1/places/search":
                query = SearchQueryParams.model_validate(params)
                payload = search_places_endpoint(
                    district=query.district,
                    internal_category=query.internal_category,
                    primary_type=query.primary_type,
                    keyword=query.keyword,
                    min_rating=query.min_rating,
                    max_budget_level=query.max_budget_level,
                    indoor=query.indoor,
                    open_now=query.open_now,
                    sort=query.sort,
                    limit=query.limit,
                    offset=query.offset,
                    db=self.session,
                )
            elif path == "/api/v1/places/nearby":
                query = NearbyQueryParams.model_validate(params)
                payload = nearby_places_endpoint(
                    lat=query.lat,
                    lng=query.lng,
                    radius_m=query.radius_m,
                    internal_category=query.internal_category,
                    primary_type=query.primary_type,
                    min_rating=query.min_rating,
                    max_budget_level=query.max_budget_level,
                    limit=query.limit,
                    sort=query.sort,
                    db=self.session,
                )
            elif path == "/api/v1/places/stats":
                payload = place_stats_endpoint(db=self.session)
            elif path == "/api/v1/places/categories":
                payload = place_categories_endpoint()
            elif path.startswith("/api/v1/places/"):
                place_id = int(path.rsplit("/", 1)[-1])
                payload = PlaceDetail.model_validate(
                    get_place(place_id=place_id, db=self.session)
                )
            else:
                raise AssertionError(f"Unsupported GET path: {path}")
        except ValidationError as exc:
            return DirectResponse(422, {"detail": exc.errors()})
        except HTTPException as exc:
            return DirectResponse(exc.status_code, {"detail": exc.detail})

        return DirectResponse(200, payload)

    def post(self, path: str, json: dict | None = None) -> DirectResponse:
        json = json or {}

        try:
            if path == "/api/v1/places/recommend":
                request = RecommendRequest.model_validate(json)
                payload = recommend_places_endpoint(request=request, db=self.session)
            elif path == "/api/v1/places/batch":
                request = BatchRequest.model_validate(json)
                payload = batch_places_endpoint(request=request, db=self.session)
            else:
                raise AssertionError(f"Unsupported POST path: {path}")
        except ValidationError as exc:
            return DirectResponse(422, {"detail": exc.errors()})
        except HTTPException as exc:
            return DirectResponse(exc.status_code, {"detail": exc.detail})

        return DirectResponse(200, payload)
