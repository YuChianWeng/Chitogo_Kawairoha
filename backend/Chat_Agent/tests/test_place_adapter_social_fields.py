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


class PlaceAdapterSocialFieldsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _build_settings(self) -> Settings:
        with patch.dict(os.environ, build_env(), clear=True):
            return Settings()

    async def test_search_normalizes_social_fields_into_tool_place(self) -> None:
        settings = self._build_settings()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 42,
                            "display_name": "Moonlit Bistro",
                            "internal_category": "food",
                            "vibe_tags": ["romantic", "quiet"],
                            "mention_count": 9,
                            "sentiment_score": 0.82,
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(keyword="date night")

        self.assertEqual(result.status, "ok")
        place = result.items[0]
        self.assertEqual(place.vibe_tags, ["romantic", "quiet"])
        self.assertEqual(place.mention_count, 9)
        self.assertEqual(place.sentiment_score, 0.82)
        self.assertEqual(place.raw_payload["vibe_tags"], ["romantic", "quiet"])

    async def test_search_keeps_social_fields_optional_when_missing(self) -> None:
        settings = self._build_settings()

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "items": [{"id": 7, "display_name": "Legacy Cafe"}],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                },
            )

        adapter = PlaceToolAdapter(settings=settings, transport=mock_transport(handler))

        result = await adapter.search_places(keyword="coffee")

        self.assertEqual(result.status, "ok")
        place = result.items[0]
        self.assertIsNone(place.vibe_tags)
        self.assertIsNone(place.mention_count)
        self.assertIsNone(place.sentiment_score)
