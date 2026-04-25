from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.tools.models import (
    CategoryItem,
    CategoryListResult,
    LodgingCandidateItem,
    LodgingCandidatesResult,
    LodgingLegalCheckResult,
    LodgingLegalInfo,
    PlaceListResult,
    PlaceSort,
    PlaceStatsResult,
    ToolPlace,
    VibeTagItem,
    VibeTagListResult,
)

_SEARCH_PATH = "/api/v1/places/search"
_RECOMMEND_PATH = "/api/v1/places/recommend"
_BATCH_PATH = "/api/v1/places/batch"
_NEARBY_PATH = "/api/v1/places/nearby"
_CATEGORIES_PATH = "/api/v1/places/categories"
_VIBE_TAGS_PATH = "/api/v1/places/vibe-tags"
_LODGING_CHECK_PATH = "/api/v1/lodgings/check"
_LODGING_CANDIDATES_PATH = "/api/v1/lodgings/candidates"
_STATS_PATH = "/api/v1/places/stats"


class PlaceToolAdapter:
    """Thin async adapter over the external Place Data Service."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def search_places(
        self,
        *,
        district: str | None = None,
        internal_category: str | None = None,
        primary_type: str | None = None,
        keyword: str | None = None,
        min_rating: float | None = None,
        max_budget_level: int | None = None,
        indoor: bool | None = None,
        open_now: bool | None = None,
        vibe_tags: list[str] | None = None,
        min_mentions: int | None = None,
        sort: PlaceSort = "rating_desc",
        limit: int = 20,
        offset: int = 0,
    ) -> PlaceListResult:
        payload, error = await self._request_json(
            "GET",
            _SEARCH_PATH,
            params=self._compact_params(
                district=district,
                internal_category=internal_category,
                primary_type=primary_type,
                keyword=keyword,
                min_rating=min_rating,
                max_budget_level=max_budget_level,
                indoor=indoor,
                open_now=open_now,
                vibe_tag=vibe_tags,
                min_mentions=min_mentions,
                sort=sort,
                limit=limit,
                offset=offset,
            ),
        )
        return self._build_place_list_result(payload, error=error)

    async def recommend_places(
        self,
        *,
        districts: list[str] | None = None,
        internal_category: str | None = None,
        min_rating: float | None = None,
        max_budget_level: int | None = None,
        indoor: bool | None = None,
        open_now: bool | None = None,
        limit: int = 10,
    ) -> PlaceListResult:
        payload, error = await self._request_json(
            "POST",
            _RECOMMEND_PATH,
            json_body=self._compact_dict(
                districts=districts,
                internal_category=internal_category,
                min_rating=min_rating,
                max_budget_level=max_budget_level,
                indoor=indoor,
                open_now=open_now,
                limit=limit,
            ),
        )
        return self._build_place_list_result(payload, error=error)

    async def batch_get_places(self, *, place_ids: list[int]) -> PlaceListResult:
        payload, error = await self._request_json(
            "POST",
            _BATCH_PATH,
            json_body={"place_ids": place_ids},
        )
        return self._build_place_list_result(
            payload,
            error=error,
            total_key=None,
            limit_key=None,
            offset_key=None,
        )

    async def nearby_places(
        self,
        *,
        lat: float,
        lng: float,
        radius_m: int,
        internal_category: str | None = None,
        primary_type: str | None = None,
        min_rating: float | None = None,
        max_budget_level: int | None = None,
        limit: int = 20,
        sort: str = "distance_asc",
    ) -> PlaceListResult:
        payload, error = await self._request_json(
            "GET",
            _NEARBY_PATH,
            params=self._compact_dict(
                lat=lat,
                lng=lng,
                radius_m=radius_m,
                internal_category=internal_category,
                primary_type=primary_type,
                min_rating=min_rating,
                max_budget_level=max_budget_level,
                limit=limit,
                sort=sort,
            ),
        )
        return self._build_place_list_result(payload, error=error, offset_key=None)

    async def get_categories(self) -> CategoryListResult:
        payload, error = await self._request_json("GET", _CATEGORIES_PATH)
        if error is not None:
            return CategoryListResult(status="error", error=error)
        if not isinstance(payload, dict) or not isinstance(payload.get("categories"), list):
            return CategoryListResult(status="error", error="malformed_payload")

        categories = [
            CategoryItem.model_validate(item)
            for item in payload["categories"]
            if isinstance(item, dict)
        ]
        if not categories:
            return CategoryListResult(status="empty")
        return CategoryListResult(status="ok", categories=categories)

    async def get_vibe_tags(
        self,
        *,
        district: str | None = None,
        internal_category: str | None = None,
        primary_type: str | None = None,
        limit: int = 50,
    ) -> VibeTagListResult:
        payload, error = await self._request_json(
            "GET",
            _VIBE_TAGS_PATH,
            params=self._compact_dict(
                district=district,
                internal_category=internal_category,
                primary_type=primary_type,
                limit=limit,
            ),
        )
        if error is not None:
            return VibeTagListResult(status="error", error=error)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return VibeTagListResult(status="error", error="malformed_payload")

        raw_items = payload["items"]
        if any(not isinstance(item, dict) for item in raw_items):
            return VibeTagListResult(status="error", error="malformed_payload")

        try:
            items = [VibeTagItem.model_validate(item) for item in raw_items]
            response_limit = int(payload.get("limit", limit) or limit)
            scope = dict(payload.get("scope") or {})
        except (TypeError, ValueError, ValidationError):
            return VibeTagListResult(status="error", error="malformed_payload")

        if not items:
            return VibeTagListResult(status="empty", limit=response_limit, scope=scope)
        return VibeTagListResult(
            status="ok",
            items=items,
            limit=response_limit,
            scope=scope,
        )

    async def check_lodging_legal_status(
        self,
        *,
        name: str,
        phone: str | None = None,
        district: str | None = None,
    ) -> LodgingLegalCheckResult:
        """Check if a lodging is legally registered in the government list."""
        payload, error = await self._request_json(
            "GET",
            _LODGING_CHECK_PATH,
            params=self._compact_dict(name=name, phone=phone, district=district),
        )
        if error is not None:
            return LodgingLegalCheckResult(status="error", error=error)
        if not isinstance(payload, dict):
            return LodgingLegalCheckResult(status="error", error="malformed_payload")
        try:
            is_legal = bool(payload.get("is_legal", False))
            lodging_raw = payload.get("lodging")
            lodging = LodgingLegalInfo.model_validate(lodging_raw) if lodging_raw else None
            return LodgingLegalCheckResult(
                status="ok",
                is_legal=is_legal,
                lodging=lodging,
                match_type=payload.get("match_type"),
                confidence=payload.get("confidence"),
            )
        except (TypeError, ValueError, ValidationError):
            return LodgingLegalCheckResult(status="error", error="malformed_payload")

    async def search_lodging_candidates(
        self,
        *,
        name: str,
        limit: int = 3,
    ) -> LodgingCandidatesResult:
        """Return top-N lodging candidates by name similarity."""
        payload, error = await self._request_json(
            "GET",
            _LODGING_CANDIDATES_PATH,
            params=self._compact_dict(name=name, limit=limit),
        )
        if error is not None:
            return LodgingCandidatesResult(status="error", error=error)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return LodgingCandidatesResult(status="error", error="malformed_payload")
        try:
            items = [
                LodgingCandidateItem(
                    name=item["lodging"]["name"],
                    district=item["lodging"].get("district"),
                    address=item["lodging"].get("address"),
                    confidence=float(item["confidence"]),
                )
                for item in payload["items"]
                if isinstance(item, dict) and isinstance(item.get("lodging"), dict)
            ]
        except (KeyError, TypeError, ValueError):
            return LodgingCandidatesResult(status="error", error="malformed_payload")
        if not items:
            return LodgingCandidatesResult(status="empty")
        return LodgingCandidatesResult(status="ok", items=items)

    async def get_stats(self) -> PlaceStatsResult:
        payload, error = await self._request_json("GET", _STATS_PATH)
        if error is not None:
            return PlaceStatsResult(status="error", error=error)
        if not isinstance(payload, dict):
            return PlaceStatsResult(status="error", error="malformed_payload")
        try:
            result = PlaceStatsResult(
                status="ok" if int(payload.get("total_places", 0)) > 0 else "empty",
                total_places=int(payload.get("total_places", 0)),
                by_district=dict(payload.get("by_district") or {}),
                by_internal_category=dict(payload.get("by_internal_category") or {}),
                by_primary_type=dict(payload.get("by_primary_type") or {}),
            )
        except (TypeError, ValueError):
            return PlaceStatsResult(status="error", error="malformed_payload")
        return result

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[Any | None, str | None]:
        last_error: str | None = None
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.place_service_base_url,
                timeout=self.settings.place_service_timeout_sec,
                transport=self._transport,
            ) as client:
                for attempt in range(2):
                    response = await client.request(
                        method,
                        path,
                        params=params,
                        json=json_body,
                    )

                    if response.status_code >= 500 and attempt == 0:
                        last_error = f"http_{response.status_code}"
                        continue
                    if response.status_code >= 400:
                        return None, f"http_{response.status_code}"
                    try:
                        return response.json(), None
                    except ValueError:
                        return None, "malformed_json"
        except httpx.TimeoutException:
            return None, "timeout"
        except httpx.HTTPError as exc:
            return None, exc.__class__.__name__
        return None, last_error or "http_500"

    def _build_place_list_result(
        self,
        payload: Any,
        *,
        error: str | None,
        total_key: str | None = "total",
        limit_key: str | None = "limit",
        offset_key: str | None = "offset",
    ) -> PlaceListResult:
        if error is not None:
            return PlaceListResult(status="error", error=error)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return PlaceListResult(status="error", error="malformed_payload")

        items = [
            place
            for item in payload["items"]
            if isinstance(item, dict)
            for place in [self._normalize_place(item)]
            if place is not None
        ]
        try:
            total = (
                len(items) if total_key is None else int(payload.get(total_key, len(items)) or 0)
            )
            limit = (
                None
                if limit_key is None
                else int(payload.get(limit_key, len(items)) or len(items))
            )
            offset = None if offset_key is None else int(payload.get(offset_key, 0) or 0)
        except (TypeError, ValueError):
            return PlaceListResult(status="error", error="malformed_payload")

        status = "ok" if items else "empty"
        return PlaceListResult(
            status=status,
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _normalize_place(payload: dict[str, Any]) -> ToolPlace | None:
        venue_id = payload.get("id") or payload.get("venue_id") or payload.get("place_id")
        name = payload.get("display_name") or payload.get("name") or payload.get("venue_name")
        if venue_id is None or not isinstance(name, str) or not name.strip():
            return None
        return ToolPlace(
            venue_id=venue_id,
            name=name.strip(),
            category=payload.get("internal_category") or payload.get("category"),
            district=payload.get("district"),
            primary_type=payload.get("primary_type"),
            formatted_address=payload.get("formatted_address"),
            lat=payload.get("latitude", payload.get("lat")),
            lng=payload.get("longitude", payload.get("lng")),
            rating=payload.get("rating"),
            user_rating_count=payload.get("user_rating_count"),
            price_level=payload.get("price_level"),
            budget_level=payload.get("budget_level"),
            indoor=payload.get("indoor"),
            outdoor=payload.get("outdoor"),
            google_maps_uri=payload.get("google_maps_uri"),
            recommendation_score=payload.get("recommendation_score"),
            distance_m=payload.get("distance_m"),
            vibe_tags=payload.get("vibe_tags"),
            mention_count=payload.get("mention_count"),
            sentiment_score=payload.get("sentiment_score"),
            raw_payload=payload,
        )

    @staticmethod
    def _compact_dict(**kwargs: Any) -> dict[str, Any]:
        return {key: value for key, value in kwargs.items() if value is not None}

    @staticmethod
    def _compact_params(**kwargs: Any) -> list[tuple[str, Any]]:
        params: list[tuple[str, Any]] = []
        for key, value in kwargs.items():
            if value is None:
                continue
            if isinstance(value, list):
                params.extend((key, item) for item in value if item is not None)
                continue
            params.append((key, value))
        return params


place_tool_adapter = PlaceToolAdapter()

__all__ = ["PlaceToolAdapter", "place_tool_adapter"]
