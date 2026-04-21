from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import httpx

from app.core.config import Settings, clear_settings_cache
from app.tools.route_adapter import RouteToolAdapter


def build_env(route_provider: str = "google_maps") -> dict[str, str]:
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
            "ROUTE_PROVIDER": route_provider,
        }
    )
    return env


class RouteToolAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _build_settings(self, *, route_provider: str = "google_maps") -> Settings:
        with patch.dict(os.environ, build_env(route_provider=route_provider), clear=True):
            return Settings()

    async def test_successful_route_result_from_google_maps(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/maps/api/directions/json")
            self.assertEqual(request.url.params["mode"], "transit")
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "routes": [
                        {
                            "legs": [
                                {
                                    "distance": {"value": 3200},
                                    "duration": {"value": 900},
                                }
                            ]
                        }
                    ],
                },
            )

        adapter = RouteToolAdapter(settings=settings, transport=httpx.MockTransport(handler))

        result = await adapter.estimate_route(
            origin_lat=25.0478,
            origin_lng=121.5170,
            destination_lat=25.0340,
            destination_lng=121.5645,
            transport_mode="transit",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.provider, "google_maps")
        self.assertEqual(result.distance_m, 3200)
        self.assertEqual(result.duration_min, 15)
        self.assertFalse(result.estimated)

    async def test_route_falls_back_to_haversine_when_provider_unavailable(self) -> None:
        settings = self._build_settings()

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable", request=request)

        adapter = RouteToolAdapter(settings=settings, transport=httpx.MockTransport(handler))

        result = await adapter.estimate_route(
            origin_lat=25.0478,
            origin_lng=121.5170,
            destination_lat=25.0340,
            destination_lng=121.5645,
            transport_mode="transit",
        )

        self.assertEqual(result.status, "fallback")
        self.assertEqual(result.provider, "haversine")
        self.assertTrue(result.estimated)
        self.assertGreater(result.distance_m, 0)
        self.assertGreater(result.duration_min, 0)

    async def test_route_uses_haversine_when_fallback_provider_is_configured(self) -> None:
        settings = self._build_settings(route_provider="fallback")
        adapter = RouteToolAdapter(settings=settings)

        result = await adapter.estimate_route(
            origin_lat=25.0478,
            origin_lng=121.5170,
            destination_lat=25.0340,
            destination_lng=121.5645,
            transport_mode="transit",
        )

        self.assertEqual(result.status, "fallback")
        self.assertEqual(result.provider, "haversine")
        self.assertTrue(result.estimated)
        self.assertGreater(result.distance_m, 0)
        self.assertGreater(result.duration_min, 0)

    async def test_transport_mode_mapping(self) -> None:
        settings = self._build_settings()
        seen_modes: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_modes.append(request.url.params["mode"])
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "routes": [
                        {
                            "legs": [
                                {
                                    "distance": {"value": 1000},
                                    "duration": {"value": 600},
                                }
                            ]
                        }
                    ],
                },
            )

        adapter = RouteToolAdapter(settings=settings, transport=httpx.MockTransport(handler))

        await adapter.estimate_route(25.0, 121.5, 25.01, 121.51, transport_mode="walk")
        await adapter.estimate_route(25.0, 121.5, 25.01, 121.51, transport_mode="taxi")

        self.assertEqual(seen_modes, ["walking", "driving"])

    async def test_invalid_coordinates_return_structured_result(self) -> None:
        settings = self._build_settings(route_provider="fallback")
        adapter = RouteToolAdapter(settings=settings)

        result = await adapter.estimate_route(
            origin_lat=200.0,
            origin_lng=121.5,
            destination_lat=25.01,
            destination_lng=121.51,
        )

        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.provider, "validation")
        self.assertEqual(result.distance_m, 0)
        self.assertEqual(result.duration_min, 0)
