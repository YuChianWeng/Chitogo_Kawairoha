from __future__ import annotations

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


class PlaceAdapterVibeTagsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _build_settings(self) -> Settings:
        with patch.dict(os.environ, build_env(), clear=True):
            return Settings()

    async def test_get_vibe_tags_success_and_scoped_params(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/v1/places/vibe-tags")
            self.assertEqual(request.url.params["district"], "信義區")
            self.assertEqual(request.url.params["internal_category"], "food")
            self.assertEqual(request.url.params["primary_type"], "japanese_restaurant")
            self.assertEqual(request.url.params["limit"], "25")
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "tag": "romantic",
                            "place_count": 12,
                            "mention_count": 38,
                        }
                    ],
                    "limit": 25,
                    "scope": {
                        "district": "信義區",
                        "internal_category": "food",
                        "primary_type": "japanese_restaurant",
                    },
                },
            )

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.get_vibe_tags(
            district="信義區",
            internal_category="food",
            primary_type="japanese_restaurant",
            limit=25,
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.limit, 25)
        self.assertEqual(result.scope["district"], "信義區")
        self.assertEqual(result.items[0].tag, "romantic")
        self.assertEqual(result.items[0].place_count, 12)
        self.assertEqual(result.items[0].mention_count, 38)

    async def test_get_vibe_tags_empty_result_is_safe(self) -> None:
        settings = self._build_settings()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "items": [],
                    "limit": 50,
                    "scope": {
                        "district": None,
                        "internal_category": None,
                        "primary_type": None,
                    },
                },
            )

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.get_vibe_tags()

        self.assertEqual(result.status, "empty")
        self.assertEqual(result.items, [])
        self.assertEqual(result.limit, 50)

    async def test_get_vibe_tags_malformed_payload_returns_error(self) -> None:
        settings = self._build_settings()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"items": [{"tag": "romantic", "place_count": "many"}]},
            )

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.get_vibe_tags()

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error, "malformed_payload")

    async def test_get_vibe_tags_timeout_returns_error(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.get_vibe_tags()

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error, "timeout")


if __name__ == "__main__":
    unittest.main()
