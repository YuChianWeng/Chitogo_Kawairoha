from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import httpx

from app.core.config import Settings, clear_settings_cache
from app.tools.place_adapter import PlaceToolAdapter


def build_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "APP_ENV": "test",
            "HOST": "127.0.0.1",
            "PORT": "8100",
            "DATA_SERVICE_BASE_URL": "http://data-service.local",
            "GEMINI_API_KEY": "gemini-test-key",
            "GOOGLE_MAPS_API_KEY": "gmaps-key",
            "CORS_ALLOW_ORIGINS": "http://localhost:5173",
            "LOG_LEVEL": "INFO",
        }
    )
    return env


def mock_transport(handler):
    return httpx.MockTransport(handler)


class PlaceToolAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _build_settings(self) -> Settings:
        with patch.dict(os.environ, build_env(), clear=True):
            return Settings()

    async def test_search_places_success(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/v1/places/search")
            self.assertEqual(request.url.params["keyword"], "cafe")
            self.assertEqual(request.url.params["sort"], "rating_desc")
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "display_name": "Cafe A",
                            "internal_category": "food",
                            "latitude": 25.0,
                            "longitude": 121.5,
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(keyword="cafe")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].venue_id, 1)
        self.assertEqual(result.items[0].name, "Cafe A")

    async def test_recommend_batch_nearby_categories_and_stats_success(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/api/v1/places/recommend":
                self.assertEqual(request.method, "POST")
                payload = json.loads(request.content.decode("utf-8"))
                self.assertEqual(payload["districts"], ["萬華區"])
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": 7,
                                "display_name": "Temple Pick",
                                "internal_category": "attraction",
                                "recommendation_score": 0.91,
                            }
                        ],
                        "total": 1,
                        "limit": 10,
                        "offset": 0,
                    },
                )
            if path == "/api/v1/places/batch":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": 7,
                                "display_name": "Temple Pick",
                                "internal_category": "attraction",
                                "latitude": 25.04,
                                "longitude": 121.51,
                            }
                        ]
                    },
                )
            if path == "/api/v1/places/nearby":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": 8,
                                "display_name": "Nearby Tea",
                                "internal_category": "food",
                                "distance_m": 120.0,
                            }
                        ],
                        "total": 1,
                        "limit": 20,
                    },
                )
            if path == "/api/v1/places/categories":
                return httpx.Response(
                    200,
                    json={
                        "categories": [
                            {
                                "value": "food",
                                "label": "Food",
                                "representative_types": ["restaurant"],
                            }
                        ]
                    },
                )
            if path == "/api/v1/places/stats":
                return httpx.Response(
                    200,
                    json={
                        "total_places": 123,
                        "by_district": {"萬華區": 12},
                        "by_internal_category": {"food": 44},
                        "by_primary_type": {"restaurant": 30},
                    },
                )
            self.fail(f"Unexpected path: {path}")

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        recommend_result = await adapter.recommend_places(districts=["萬華區"])
        batch_result = await adapter.batch_get_places(place_ids=[7])
        nearby_result = await adapter.nearby_places(lat=25.04, lng=121.51, radius_m=500)
        categories_result = await adapter.get_categories()
        stats_result = await adapter.get_stats()

        self.assertEqual(recommend_result.items[0].recommendation_score, 0.91)
        self.assertEqual(batch_result.items[0].venue_id, 7)
        self.assertIsNone(batch_result.limit)
        self.assertIsNone(batch_result.offset)
        self.assertEqual(nearby_result.items[0].distance_m, 120.0)
        self.assertEqual(categories_result.categories[0].value, "food")
        self.assertEqual(stats_result.total_places, 123)

    async def test_non_200_response_returns_error_result(self) -> None:
        settings = self._build_settings()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "service unavailable"})

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(keyword="cafe")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.items, [])
        self.assertIn("503", result.error or "")

    async def test_timeout_returns_error_result(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(keyword="cafe")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error, "timeout")

    async def test_malformed_payload_returns_error_result(self) -> None:
        settings = self._build_settings()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(keyword="cafe")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error, "malformed_payload")

    async def test_empty_result_is_safe(self) -> None:
        settings = self._build_settings()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": [], "total": 0, "limit": 20, "offset": 0})

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(keyword="unknown")

        self.assertEqual(result.status, "empty")
        self.assertEqual(result.items, [])
        self.assertEqual(result.total, 0)
