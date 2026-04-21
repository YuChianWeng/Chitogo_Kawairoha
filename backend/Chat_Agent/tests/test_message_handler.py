from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from uuid import uuid4

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


def build_place(
    venue_id: int,
    name: str,
    *,
    district: str = "萬華區",
    category: str = "food",
    primary_type: str = "cafe",
) -> ToolPlace:
    return ToolPlace(
        venue_id=venue_id,
        name=name,
        district=district,
        category=category,
        primary_type=primary_type,
        rating=4.6,
        budget_level="mid",
    )


class StubPlaceAdapter:
    def __init__(
        self,
        *,
        recommend_result: PlaceListResult | None = None,
        search_result: PlaceListResult | None = None,
        nearby_result: PlaceListResult | None = None,
    ) -> None:
        self.recommend_result = recommend_result or PlaceListResult(
            status="ok",
            items=[build_place(1, "Cafe A"), build_place(2, "Cafe B")],
            total=2,
            limit=5,
            offset=0,
        )
        self.search_result = search_result or PlaceListResult(
            status="ok",
            items=[build_place(3, "Search Cafe")],
            total=1,
            limit=5,
            offset=0,
        )
        self.nearby_result = nearby_result or PlaceListResult(
            status="ok",
            items=[build_place(4, "Nearby Cafe")],
            total=1,
            limit=5,
            offset=0,
        )
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def search_places(self, **kwargs: object) -> PlaceListResult:
        self.calls.append(("place_search", kwargs))
        return self.search_result

    async def recommend_places(self, **kwargs: object) -> PlaceListResult:
        self.calls.append(("place_recommend", kwargs))
        return self.recommend_result

    async def batch_get_places(self, **kwargs: object) -> PlaceListResult:
        self.calls.append(("place_batch", kwargs))
        return PlaceListResult(status="empty", items=[], total=0)

    async def nearby_places(self, **kwargs: object) -> PlaceListResult:
        self.calls.append(("place_nearby", kwargs))
        return self.nearby_result

    async def get_categories(self) -> object:
        self.calls.append(("place_categories", {}))
        return None

    async def get_stats(self) -> object:
        self.calls.append(("place_stats", {}))
        return None


class StubRouteAdapter:
    async def estimate_route(self, **_: object) -> object:
        return None


class MessageHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        clear_settings_cache()
        self.store = InMemorySessionStore()
        self.manager = SessionManager(store=self.store)

    async def asyncTearDown(self) -> None:
        await self.store.clear()
        clear_settings_cache()

    def _build_handler(
        self,
        *,
        place_adapter: StubPlaceAdapter | None = None,
    ) -> tuple[MessageHandler, StubPlaceAdapter]:
        adapter = place_adapter or StubPlaceAdapter()
        registry = ToolRegistry(
            place_adapter=adapter,
            route_adapter=StubRouteAdapter(),
        )
        handler = MessageHandler(
            session_manager_instance=self.manager,
            agent_loop=AgentLoop(registry=registry),
        )
        async def disabled_generate_json(*_: object, **__: object) -> object:
            raise RuntimeError("disabled")

        handler._classifier._client.generate_json = disabled_generate_json
        handler._preference_extractor._client.generate_json = disabled_generate_json
        return handler, adapter

    async def test_clarification_path_avoids_tool_calls(self) -> None:
        handler, adapter = self._build_handler()

        response = await handler.handle(ChatMessageRequest(message="幫我排一下行程"))

        self.assertTrue(response.needs_clarification)
        self.assertEqual(response.intent.value, "GENERATE_ITINERARY")
        self.assertEqual(adapter.calls, [])

    async def test_recommendation_path_stores_assistant_turn_and_candidates(self) -> None:
        handler, adapter = self._build_handler()
        session_id = str(uuid4())

        response = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我排今晚從台北車站出發的萬華區咖啡行程",
            )
        )
        session = await self.manager.get_or_create(session_id)

        self.assertFalse(response.needs_clarification)
        self.assertEqual(response.intent.value, "GENERATE_ITINERARY")
        self.assertGreaterEqual(len(response.candidates), 1)
        self.assertIn("place_recommend", [name for name, _ in adapter.calls])
        self.assertEqual(len(session.turns), 2)
        self.assertEqual(session.turns[1].role, "assistant")
        self.assertGreaterEqual(len(session.cached_candidates), 1)

    async def test_tool_failure_degrades_gracefully(self) -> None:
        handler, adapter = self._build_handler(
            place_adapter=StubPlaceAdapter(
                recommend_result=PlaceListResult(status="error", error="timeout"),
            )
        )

        response = await handler.handle(
            ChatMessageRequest(message="幫我排今晚從台北車站出發的萬華區咖啡行程")
        )

        self.assertEqual(response.tool_results_summary.result_status, "error")
        self.assertEqual(response.candidates, [])
        self.assertIn("place_recommend", [name for name, _ in adapter.calls])
        self.assertIn("推薦資料", response.message)

    async def test_preference_persistence_across_turns(self) -> None:
        handler, adapter = self._build_handler()
        session_id = str(uuid4())

        first = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="今晚從台北車站出發，想去萬華區咖啡廳",
            )
        )
        second = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我排一下行程",
            )
        )

        self.assertEqual(first.preferences.origin, "台北車站")
        self.assertEqual(first.preferences.district, "萬華區")
        self.assertEqual(first.preferences.language, "zh-TW")
        self.assertFalse(second.needs_clarification)
        self.assertIn("place_recommend", [name for name, _ in adapter.calls])

    async def test_general_chat_fallback_does_not_call_tools(self) -> None:
        handler, adapter = self._build_handler()

        response = await handler.handle(ChatMessageRequest(message="hello there"))

        self.assertEqual(response.intent.value, "CHAT_GENERAL")
        self.assertEqual(response.candidates, [])
        self.assertIsNone(response.tool_results_summary)
        self.assertEqual(adapter.calls, [])

    async def test_replan_returns_safe_placeholder(self) -> None:
        handler, adapter = self._build_handler()

        response = await handler.handle(ChatMessageRequest(message="請換掉第二站"))

        self.assertEqual(response.intent.value, "REPLAN")
        self.assertEqual(response.candidates, [])
        self.assertIsNone(response.tool_results_summary)
        self.assertEqual(adapter.calls, [])
        self.assertIn("重排行程", response.message)
