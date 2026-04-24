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


class PlaceAdapterVibeTagParamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _build_settings(self) -> Settings:
        with patch.dict(os.environ, build_env(), clear=True):
            return Settings()

    async def test_search_emits_repeated_vibe_tag_params_and_social_sort(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/v1/places/search")
            self.assertEqual(request.url.params.get_list("vibe_tag"), ["romantic", "scenic"])
            self.assertEqual(request.url.params["min_mentions"], "3")
            self.assertEqual(request.url.params["sort"], "trend_score_desc")
            return httpx.Response(200, json={"items": [], "total": 0, "limit": 20, "offset": 0})

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(
            vibe_tags=["romantic", "scenic"],
            min_mentions=3,
            sort="trend_score_desc",
        )

        self.assertEqual(result.status, "empty")
