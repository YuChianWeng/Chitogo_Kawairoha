from __future__ import annotations

import os
import unittest
from asyncio import run
from importlib import import_module
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings, clear_settings_cache


class HealthEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = dict(os.environ)
        self.env.update(
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
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _load_create_app(self):
        import sys

        sys.modules.pop("app.main", None)
        module = import_module("app.main")
        return module.create_app

    def test_health_returns_reachable_status(self) -> None:
        from app.api.v1.health import health

        with patch.dict(os.environ, self.env, clear=True):
            settings = Settings()
            request = httpx.Request(
                "GET",
                "http://data-service.local/api/v1/places/stats",
            )
            with patch(
                "httpx.AsyncClient.get",
                new=AsyncMock(
                    return_value=httpx.Response(
                        200,
                        json={"total_places": 123},
                        request=request,
                    )
                ),
            ):
                response = run(health(settings))

        self.assertEqual(
            response,
            {
                "status": "ok",
                "service": "agent-orchestration-backend",
                "data_service": "reachable",
            },
        )

    def test_health_returns_degraded_status_on_timeout(self) -> None:
        from app.api.v1.health import health

        with patch.dict(os.environ, self.env, clear=True):
            settings = Settings()
            with patch(
                "app.api.v1.health.probe_data_service",
                new=AsyncMock(return_value=False),
            ):
                response = run(health(settings))

        self.assertEqual(response["status"], "degraded")
        self.assertEqual(response["service"], "agent-orchestration-backend")
        self.assertEqual(response["data_service"], "degraded")

    def test_app_boot_smoke(self) -> None:
        with patch.dict(os.environ, self.env, clear=True):
            create_app = self._load_create_app()
            client = TestClient(create_app())

        self.assertEqual(client.app.title, "Chitogo Chat Agent")
