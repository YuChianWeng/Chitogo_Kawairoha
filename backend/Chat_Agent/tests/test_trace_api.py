from __future__ import annotations

from asyncio import run
import os
import unittest
from unittest.mock import patch

from app.api.v1.chat import get_chat_trace, list_chat_traces
from app.chat.loop import AgentLoop
from app.chat.message_handler import MessageHandler
from app.chat.schemas import ChatMessageRequest
from app.chat.trace_store import TraceStore
from app.core.config import Settings, clear_settings_cache
from app.session.manager import SessionManager
from app.session.store import InMemorySessionStore
from app.tools.models import PlaceListResult, RouteResult, ToolPlace
from app.tools.registry import ToolRegistry
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
                    name="Cafe Trace",
                    district="萬華區",
                    category="food",
                    primary_type="cafe",
                    rating=4.7,
                    lat=25.041,
                    lng=121.501,
                ),
                ToolPlace(
                    venue_id=11,
                    name="Cafe Trace 2",
                    district="萬華區",
                    category="food",
                    primary_type="cafe",
                    rating=4.5,
                    lat=25.042,
                    lng=121.502,
                ),
                ToolPlace(
                    venue_id=12,
                    name="Cafe Trace 3",
                    district="萬華區",
                    category="food",
                    primary_type="cafe",
                    rating=4.4,
                    lat=25.043,
                    lng=121.503,
                ),
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

    async def get_vibe_tags(self, **_: object) -> object:
        return None

    async def get_stats(self) -> object:
        return None

    async def check_lodging_legal_status(self, **_: object) -> object:
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


class TraceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _build_handler(self) -> MessageHandler:
        handler = MessageHandler(
            session_manager_instance=SessionManager(store=InMemorySessionStore()),
            agent_loop=AgentLoop(
                registry=ToolRegistry(
                    place_adapter=StubPlaceAdapter(),
                    route_adapter=StubRouteAdapter(),
                )
            ),
        )
        handler._classifier._client = ScriptedClassifierClient()
        handler._preference_extractor._client = ScriptedPreferenceClient()
        handler._agent_loop._client = DisabledLLMClient()
        handler._replanner._client = DisabledLLMClient()
        return handler

    def test_trace_endpoints_return_recent_and_detail_views(self) -> None:
        env = build_env()
        with patch.dict(os.environ, env, clear=True):
            Settings()
            handler = self._build_handler()
            run(
                handler.handle(
                    ChatMessageRequest(message="幫我排今晚從台北車站出發的萬華區咖啡行程")
                )
            )

            traces = run(list_chat_traces(limit=20, session_id=None, trace_store=handler.trace_store))
            self.assertEqual(len(traces.items), 1)
            trace_id = traces.items[0].trace_id

            detail = run(get_chat_trace(trace_id=trace_id, trace_store=handler.trace_store))

        self.assertEqual(detail.trace_id, trace_id)
        self.assertEqual(detail.outcome, "itinerary_generated")
        self.assertTrue(any(step.name == "classification" for step in detail.steps))

    def test_trace_detail_returns_404_for_unknown_id(self) -> None:
        response = run(get_chat_trace(trace_id="missing-trace", trace_store=TraceStore()))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.body.decode("utf-8"), '{"error":"trace_not_found","detail":"trace_id was not found"}')
