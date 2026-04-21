from __future__ import annotations

from asyncio import run
import os
import json
import sys
import unittest
from importlib import import_module
from unittest.mock import patch

from app.chat.loop import AgentLoop
from app.chat.message_handler import MessageHandler
from app.chat.schemas import ChatMessageRequest, ChatMessageResponse
from app.core.config import Settings, clear_settings_cache
from app.orchestration.intents import Intent
from app.session.manager import SessionManager
from app.session.models import Preferences
from app.session.store import InMemorySessionStore
from app.tools.models import PlaceListResult, RouteResult, ToolPlace
from app.tools.registry import ToolRegistry
from pydantic import ValidationError
from starlette.requests import Request
from tests.fake_llm import (
    DisabledLLMClient,
    ScriptedClassifierClient,
    ScriptedPreferenceClient,
)


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
                    lat=25.041,
                    lng=121.501,
                ),
                ToolPlace(
                    venue_id=11,
                    name="Cafe API 2",
                    district="萬華區",
                    category="food",
                    primary_type="cafe",
                    rating=4.5,
                    lat=25.042,
                    lng=121.502,
                ),
                ToolPlace(
                    venue_id=12,
                    name="Cafe API 3",
                    district="萬華區",
                    category="food",
                    primary_type="cafe",
                    rating=4.4,
                    lat=25.043,
                    lng=121.503,
                )
            ],
            total=3,
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
        return RouteResult(
            distance_m=1000,
            duration_min=10,
            provider="google_maps",
            status="ok",
            transport_mode="transit",
            estimated=False,
        )


class StubMessageHandler:
    async def handle(self, _: object) -> ChatMessageResponse:
        return ChatMessageResponse(
            session_id="11111111-1111-4111-8111-111111111111",
            turn_id="22222222-2222-4222-8222-222222222222",
            intent=Intent.CHAT_GENERAL,
            needs_clarification=False,
            message="stubbed response",
            preferences=Preferences(language="en"),
            source="stub",
        )


class BrokenMessageHandler:
    async def handle(self, _: object) -> ChatMessageResponse:
        raise RuntimeError("boom")


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
            handler._classifier._client = ScriptedClassifierClient()
            handler._preference_extractor._client = ScriptedPreferenceClient()
            handler._agent_loop._client = DisabledLLMClient()
            handler._replanner._client = DisabledLLMClient()
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
        self.assertIsNotNone(response.itinerary)
        self.assertEqual(response.routing_status, "full")
        self.assertEqual(response.candidates[0].name, "Cafe API")

    def test_chat_endpoint_dependency_resolves_handler_from_app_state(self) -> None:
        env = build_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            create_app = self._load_create_app()
            app = create_app(settings)
            app.state.message_handler = StubMessageHandler()
            route_paths = {route.path for route in app.routes}
            self.assertIn("/api/v1/chat/message", route_paths)

            async def receive() -> dict[str, object]:
                return {"type": "http.request", "body": b"", "more_body": False}

            request = Request(
                {
                    "type": "http",
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/v1/chat/message",
                    "raw_path": b"/api/v1/chat/message",
                    "query_string": b"",
                    "headers": [],
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                    "app": app,
                },
                receive=receive,
            )

            from app.api.v1.chat import get_message_handler, post_chat_message

            resolved_handler = get_message_handler(request)
            response = run(post_chat_message(ChatMessageRequest(message="hello"), resolved_handler))
            body = response.model_dump()

        self.assertIn("session_id", body)
        self.assertIn("turn_id", body)
        self.assertEqual(body["intent"], "CHAT_GENERAL")
        self.assertFalse(body["needs_clarification"])
        self.assertIn("preferences", body)
        self.assertEqual(body["message"], "stubbed response")
        self.assertEqual(body["source"], "stub")

    def test_chat_endpoint_rejects_whitespace_only_message(self) -> None:
        with self.assertRaises(ValidationError):
            ChatMessageRequest(message="   ")

    def test_chat_endpoint_returns_internal_error_envelope_on_handler_exception(self) -> None:
        from app.api.v1.chat import post_chat_message

        response = run(
            post_chat_message(
                ChatMessageRequest(message="hello"),
                BrokenMessageHandler(),
            )
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(json.loads(response.body)["error"], "internal_error")
