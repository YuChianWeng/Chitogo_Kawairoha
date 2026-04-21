from __future__ import annotations

from asyncio import run
import os
import sys
import unittest
from importlib import import_module
from unittest.mock import patch

from app.chat.loop import AgentLoop
from app.chat.message_handler import MessageHandler
from app.chat.schemas import ChatMessageRequest
from app.core.config import Settings, clear_settings_cache
from app.session.manager import SessionManager
from app.session.store import InMemorySessionStore
from app.tools.models import PlaceListResult, ToolPlace
from app.tools.registry import ToolRegistry


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


class StubPlaceAdapter:
    async def search_places(self, **_: object) -> PlaceListResult:
        return PlaceListResult(
            status="ok",
            items=[
                ToolPlace(
                    venue_id=10,
                    name="Cafe API",
                    district="萬華區",
                    category="food",
                    primary_type="cafe",
                    rating=4.7,
                )
            ],
            total=1,
            limit=5,
            offset=0,
        )

    async def recommend_places(self, **_: object) -> PlaceListResult:
        return await self.search_places()

    async def batch_get_places(self, **_: object) -> PlaceListResult:
        return PlaceListResult(status="empty", items=[], total=0)

    async def nearby_places(self, **_: object) -> PlaceListResult:
        return await self.search_places()

    async def get_categories(self) -> object:
        return None

    async def get_stats(self) -> object:
        return None


class StubRouteAdapter:
    async def estimate_route(self, **_: object) -> object:
        return None


class ChatApiTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _load_create_app(self):
        sys.modules.pop("app.main", None)
        module = import_module("app.main")
        return module.create_app

    def test_chat_endpoint_happy_path(self) -> None:
        env = build_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            create_app = self._load_create_app()
            app = create_app(settings)
            handler = MessageHandler(
                session_manager_instance=SessionManager(store=InMemorySessionStore()),
                agent_loop=AgentLoop(
                    registry=ToolRegistry(
                        place_adapter=StubPlaceAdapter(),
                        route_adapter=StubRouteAdapter(),
                    ),
                    settings=settings,
                ),
            )
            async def disabled_generate_json(*_: object, **__: object) -> object:
                raise RuntimeError("disabled")

            handler._classifier._client.generate_json = disabled_generate_json
            handler._preference_extractor._client.generate_json = disabled_generate_json
            route_paths = {route.path for route in app.routes}
            self.assertIn("/api/v1/chat/message", route_paths)

            from app.api.v1.chat import post_chat_message

            response = run(
                post_chat_message(
                    ChatMessageRequest(message="幫我排今晚從台北車站出發的萬華區咖啡行程"),
                    handler,
                )
            )

        self.assertTrue(hasattr(response, "session_id"))
        self.assertEqual(response.intent.value, "GENERATE_ITINERARY")
        self.assertFalse(response.needs_clarification)
        self.assertGreaterEqual(len(response.candidates), 1)
        self.assertEqual(response.candidates[0].name, "Cafe API")
