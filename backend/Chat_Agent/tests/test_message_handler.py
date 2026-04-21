from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.chat.loop import AgentLoop
from app.chat.message_handler import MessageHandler
from app.chat.schemas import ChatMessageRequest, ChatUserContext
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


def build_place(
    venue_id: int,
    name: str,
    *,
    district: str = "萬華區",
    category: str = "food",
    primary_type: str = "cafe",
    lat: float | None = None,
    lng: float | None = None,
) -> ToolPlace:
    return ToolPlace(
        venue_id=venue_id,
        name=name,
        district=district,
        category=category,
        primary_type=primary_type,
        rating=4.6,
        budget_level="mid",
        lat=lat if lat is not None else 25.0400 + (venue_id * 0.001),
        lng=lng if lng is not None else 121.5000 + (venue_id * 0.001),
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
            items=[
                build_place(1, "Cafe A"),
                build_place(2, "Cafe B"),
                build_place(3, "Cafe C"),
                build_place(4, "Cafe D"),
            ],
            total=4,
            limit=5,
            offset=0,
        )
        self.search_result = search_result or PlaceListResult(
            status="ok",
            items=[build_place(5, "Search Cafe")],
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
    def __init__(
        self,
        *,
        status: str = "ok",
        duration_min: int = 12,
        distance_m: int = 1200,
    ) -> None:
        self.status = status
        self.duration_min = duration_min
        self.distance_m = distance_m
        self.calls: list[dict[str, object]] = []

    async def estimate_route(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        provider = "google_maps" if self.status == "ok" else "haversine"
        return RouteResult(
            distance_m=self.distance_m,
            duration_min=self.duration_min,
            provider=provider,
            status=self.status,  # type: ignore[arg-type]
            transport_mode="transit",
            estimated=self.status != "ok",
        )


class BrokenComposer:
    def compose_general_chat(self, *, preferences: object) -> str:
        raise RuntimeError("composer exploded")


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
        route_adapter: StubRouteAdapter | None = None,
        composer: object | None = None,
    ) -> tuple[MessageHandler, StubPlaceAdapter, StubRouteAdapter]:
        adapter = place_adapter or StubPlaceAdapter()
        route = route_adapter or StubRouteAdapter()
        registry = ToolRegistry(
            place_adapter=adapter,
            route_adapter=route,
        )
        handler = MessageHandler(
            session_manager_instance=self.manager,
            agent_loop=AgentLoop(registry=registry),
            composer=composer,
            trace_store=TraceStore(max_items=20),
        )
        handler._classifier._client = ScriptedClassifierClient()
        handler._preference_extractor._client = ScriptedPreferenceClient()
        handler._agent_loop._client = DisabledLLMClient()
        handler._replanner._client = DisabledLLMClient()
        return handler, adapter, route

    async def _latest_trace(self, handler: MessageHandler):
        summaries = await handler.trace_store.list_recent(limit=1)
        self.assertEqual(len(summaries), 1)
        trace = await handler.trace_store.get(summaries[0].trace_id)
        self.assertIsNotNone(trace)
        return trace

    async def test_clarification_path_avoids_tool_calls(self) -> None:
        handler, adapter, _ = self._build_handler()

        response = await handler.handle(ChatMessageRequest(message="幫我排一下行程"))

        self.assertTrue(response.needs_clarification)
        self.assertEqual(response.intent.value, "GENERATE_ITINERARY")
        self.assertEqual(adapter.calls, [])

    async def test_itinerary_generation_persists_itinerary_and_routes(self) -> None:
        handler, adapter, route_adapter = self._build_handler()
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
        self.assertIsNotNone(response.itinerary)
        self.assertEqual(response.routing_status, "full")
        self.assertGreaterEqual(len(response.candidates), 1)
        self.assertIn("place_recommend", [name for name, _ in adapter.calls])
        self.assertGreaterEqual(len(route_adapter.calls), 1)
        self.assertEqual(len(session.turns), 2)
        self.assertEqual(session.turns[1].role, "assistant")
        self.assertGreaterEqual(len(session.cached_candidates), 1)
        self.assertIsNotNone(session.latest_itinerary)
        self.assertEqual(session.latest_itinerary.model_dump(), response.itinerary.model_dump())

    async def test_itinerary_generation_creates_structured_trace(self) -> None:
        handler, _, _ = self._build_handler()

        response = await handler.handle(
            ChatMessageRequest(message="幫我排今晚從台北車站出發的萬華區咖啡行程")
        )
        trace = await self._latest_trace(handler)
        step_names = [step.name for step in trace.steps]

        self.assertEqual(trace.intent, response.intent.value)
        self.assertEqual(trace.outcome, "itinerary_generated")
        self.assertEqual(trace.final_status, "success")
        self.assertGreaterEqual(trace.duration_ms, 0)
        self.assertIn("classification", step_names)
        self.assertIn("preferences.extract", step_names)
        self.assertIn("tool.place_recommend", step_names)
        self.assertIn("tool.route_estimate", step_names)
        self.assertIn("itinerary.build", step_names)

    async def test_tool_failure_degrades_gracefully(self) -> None:
        handler, adapter, _ = self._build_handler(
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

    async def test_tool_failure_is_captured_in_trace(self) -> None:
        handler, _, _ = self._build_handler(
            place_adapter=StubPlaceAdapter(
                recommend_result=PlaceListResult(status="error", error="timeout"),
            )
        )

        response = await handler.handle(
            ChatMessageRequest(message="幫我排今晚從台北車站出發的萬華區咖啡行程")
        )
        trace = await self._latest_trace(handler)
        tool_step = next(step for step in trace.steps if step.name == "tool.place_recommend")

        self.assertEqual(response.tool_results_summary.result_status, "error")
        self.assertEqual(trace.outcome, "tool_error_degraded")
        self.assertEqual(tool_step.status, "error")
        self.assertEqual(tool_step.summary, "timeout")

    async def test_preference_persistence_across_turns(self) -> None:
        handler, adapter, _ = self._build_handler()
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
        handler, adapter, _ = self._build_handler()

        response = await handler.handle(ChatMessageRequest(message="hello there"))

        self.assertEqual(response.intent.value, "CHAT_GENERAL")
        self.assertEqual(response.candidates, [])
        self.assertIsNone(response.tool_results_summary)
        self.assertEqual(adapter.calls, [])

    async def test_clarification_trace_marks_tools_skipped(self) -> None:
        handler, _, _ = self._build_handler()

        response = await handler.handle(ChatMessageRequest(message="幫我排一下行程"))
        trace = await self._latest_trace(handler)

        self.assertTrue(response.needs_clarification)
        self.assertEqual(trace.final_status, "clarification")
        self.assertIn(
            ("orchestration.tools", "skipped"),
            [(step.name, step.status) for step in trace.steps],
        )

    async def test_explain_uses_cached_candidates_from_previous_turn(self) -> None:
        handler, adapter, _ = self._build_handler()
        session_id = str(uuid4())

        first = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我排今晚從台北車站出發的萬華區咖啡行程",
            )
        )
        session = await self.manager.get_or_create(session_id)
        second = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="為什麼選這些地方？",
            )
        )

        self.assertGreaterEqual(len(first.candidates), 1)
        self.assertGreaterEqual(len(session.cached_candidates), 1)
        self.assertEqual(second.intent.value, "EXPLAIN")
        self.assertIn("Cafe A", second.message)
        self.assertIn("地區", second.message)
        self.assertEqual([name for name, _ in adapter.calls].count("place_recommend"), 1)

    async def test_replan_without_existing_itinerary_requests_clarification(self) -> None:
        handler, adapter, _ = self._build_handler()

        response = await handler.handle(ChatMessageRequest(message="請換掉第二站"))

        self.assertEqual(response.intent.value, "REPLAN")
        self.assertEqual(response.candidates, [])
        self.assertIsNone(response.tool_results_summary)
        self.assertEqual(adapter.calls, [])
        self.assertTrue(response.needs_clarification)
        self.assertIn("還沒有可調整的行程", response.message)

    async def test_ambiguous_replan_requests_clarification(self) -> None:
        handler, adapter, _ = self._build_handler()
        session_id = str(uuid4())

        await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我排今晚從台北車站出發的萬華區咖啡行程",
            )
        )
        response = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我改一下行程",
            )
        )

        self.assertEqual(response.intent.value, "REPLAN")
        self.assertTrue(response.needs_clarification)
        self.assertIn("哪一站", response.message)

    async def test_nearby_message_with_missing_coordinates_skips_nearby(self) -> None:
        handler, adapter, _ = self._build_handler()

        response = await handler.handle(
            ChatMessageRequest(
                message="推薦我附近的咖啡廳",
                user_context=ChatUserContext(),
            )
        )

        self.assertFalse(response.needs_clarification)
        self.assertNotIn("place_nearby", [name for name, _ in adapter.calls])

    async def test_replan_replace_stop_updates_itinerary_and_preserves_untouched_stops(self) -> None:
        handler, _, route_adapter = self._build_handler()
        session_id = str(uuid4())

        first = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我排今晚從台北車站出發的萬華區咖啡行程",
            )
        )
        second = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="換掉第一站",
            )
        )

        self.assertIsNotNone(first.itinerary)
        self.assertIsNotNone(second.itinerary)
        self.assertNotEqual(
            first.itinerary.stops[0].venue_id,
            second.itinerary.stops[0].venue_id,
        )
        self.assertEqual(
            first.itinerary.stops[1].model_dump(),
            second.itinerary.stops[1].model_dump(),
        )
        self.assertEqual(
            first.itinerary.stops[2].model_dump(),
            second.itinerary.stops[2].model_dump(),
        )
        self.assertGreaterEqual(len(route_adapter.calls), 3)

    async def test_replan_creates_trace_steps(self) -> None:
        handler, _, _ = self._build_handler()
        session_id = str(uuid4())

        await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我排今晚從台北車站出發的萬華區咖啡行程",
            )
        )
        response = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="換掉第一站",
            )
        )
        traces = await handler.trace_store.list_recent(limit=2)
        trace = await handler.trace_store.get(traces[0].trace_id)
        step_names = [step.name for step in trace.steps]

        self.assertEqual(response.intent.value, "REPLAN")
        self.assertEqual(trace.intent, "REPLAN")
        self.assertEqual(trace.outcome, "replan_applied")
        self.assertIn("replan.parse_request", step_names)
        self.assertIn("replan.apply", step_names)
        self.assertIn("replan.rebuild_itinerary", step_names)

    async def test_replan_remove_last_stop_updates_itinerary(self) -> None:
        handler, _, _ = self._build_handler()
        session_id = str(uuid4())

        first = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="幫我排今晚從台北車站出發的萬華區咖啡行程",
            )
        )
        second = await handler.handle(
            ChatMessageRequest(
                session_id=session_id,
                message="刪掉最後一站",
            )
        )

        self.assertIsNotNone(first.itinerary)
        self.assertIsNotNone(second.itinerary)
        self.assertEqual(len(second.itinerary.stops), len(first.itinerary.stops) - 1)
        self.assertEqual(
            [stop.stop_index for stop in second.itinerary.stops],
            list(range(len(second.itinerary.stops))),
        )

    async def test_concurrent_requests_same_session_keep_state_consistent(self) -> None:
        handler, _, _ = self._build_handler()
        session_id = str(uuid4())

        await asyncio.gather(
            handler.handle(
                ChatMessageRequest(
                    session_id=session_id,
                    message="幫我排今晚從台北車站出發的萬華區咖啡行程",
                )
            ),
            handler.handle(
                ChatMessageRequest(
                    session_id=session_id,
                    message="幫我排今晚從台北車站出發的萬華區咖啡行程",
                )
            ),
        )
        session = await self.manager.get_or_create(session_id)
        traces = await handler.trace_store.list_recent(limit=10, session_id=session_id)

        self.assertEqual(len(session.turns), 4)
        self.assertEqual(len(traces), 2)
        self.assertIsNotNone(session.latest_itinerary)

    async def test_unexpected_internal_error_records_trace_then_raises(self) -> None:
        handler, _, _ = self._build_handler(composer=BrokenComposer())

        with self.assertRaises(RuntimeError):
            await handler.handle(ChatMessageRequest(message="hello there"))

        trace = await self._latest_trace(handler)

        self.assertEqual(trace.final_status, "error")
        self.assertEqual(trace.error_summary, "RuntimeError")
