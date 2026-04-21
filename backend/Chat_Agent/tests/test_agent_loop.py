from __future__ import annotations

import unittest

from app.chat.loop import AgentLoop
from app.orchestration.intents import Intent
from app.session.models import Preferences
from app.tools.models import PlaceListResult, RouteResult, ToolPlace
from app.tools.registry import ToolRegistry
from tests.fake_llm import StaticJSONClient


def build_place(venue_id: int, name: str) -> ToolPlace:
    return ToolPlace(
        venue_id=venue_id,
        name=name,
        district="萬華區",
        category="food",
        primary_type="cafe",
        rating=4.6,
        lat=25.04,
        lng=121.50,
    )


class StubPlaceAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.search_result = PlaceListResult(
            status="ok",
            items=[build_place(1, "Search Cafe")],
            total=1,
            limit=5,
            offset=0,
        )
        self.recommend_result = PlaceListResult(
            status="ok",
            items=[build_place(2, "Recommend Cafe")],
            total=1,
            limit=5,
            offset=0,
        )
        self.nearby_result = PlaceListResult(
            status="ok",
            items=[build_place(3, "Nearby Cafe")],
            total=1,
            limit=5,
            offset=0,
        )

    async def search_places(self, **kwargs: object) -> PlaceListResult:
        self.calls.append(("place_search", kwargs))
        return self.search_result

    async def recommend_places(self, **kwargs: object) -> PlaceListResult:
        self.calls.append(("place_recommend", kwargs))
        return self.recommend_result

    async def nearby_places(self, **kwargs: object) -> PlaceListResult:
        self.calls.append(("place_nearby", kwargs))
        return self.nearby_result

    async def batch_get_places(self, **_: object) -> PlaceListResult:
        return PlaceListResult(status="empty", items=[], total=0)

    async def get_categories(self) -> object:
        return None

    async def get_stats(self) -> object:
        return None


class StubRouteAdapter:
    async def estimate_route(self, **_: object) -> RouteResult:
        return RouteResult(
            distance_m=1000,
            duration_min=10,
            provider="google_maps",
            status="ok",
            transport_mode="transit",
            estimated=False,
        )


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.place_adapter = StubPlaceAdapter()
        self.loop = AgentLoop(
            registry=ToolRegistry(
                place_adapter=self.place_adapter,
                route_adapter=StubRouteAdapter(),
            )
        )

    async def test_valid_llm_plan_is_used(self) -> None:
        self.loop._client = StaticJSONClient(
            {
                "tool": "place_search",
                "params": {
                    "district": "萬華區",
                    "internal_category": "food",
                    "keyword": "coffee",
                    "limit": 3,
                },
            }
        )

        result = await self.loop.run(
            intent=Intent.CHAT_GENERAL,
            message="找萬華區咖啡廳",
            preferences=Preferences(language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][0], "place_search")
        self.assertEqual(self.place_adapter.calls[0][1]["district"], "萬華區")
        self.assertEqual(self.place_adapter.calls[0][1]["internal_category"], "food")
        self.assertEqual(self.place_adapter.calls[0][1]["keyword"], "coffee")
        self.assertEqual(self.place_adapter.calls[0][1]["limit"], 3)

    async def test_interest_tag_mapping_overrides_llm_search_params(self) -> None:
        self.loop._client = StaticJSONClient(
            {
                "tool": "place_search",
                "params": {
                    "district": "大安區",
                    "internal_category": "nightlife",
                    "keyword": "咖啡廳",
                    "limit": 4,
                },
            }
        )

        result = await self.loop.run(
            intent=Intent.GENERATE_ITINERARY,
            message="我想去大安區咖啡廳",
            preferences=Preferences(
                district="大安區",
                interest_tags=["cafes"],
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][0], "place_search")
        self.assertEqual(self.place_adapter.calls[0][1]["district"], "大安區")
        self.assertEqual(self.place_adapter.calls[0][1]["internal_category"], "food")
        self.assertEqual(self.place_adapter.calls[0][1]["keyword"], "cafe")
        self.assertEqual(self.place_adapter.calls[0][1]["limit"], 4)

    async def test_planned_search_uses_llm_keyword_when_no_interest_mapping_exists(self) -> None:
        self.loop._client = StaticJSONClient(
            {
                "tool": "place_search",
                "params": {
                    "district": "大安區",
                    "internal_category": "food",
                    "keyword": "咖啡廳",
                },
            }
        )

        result = await self.loop.run(
            intent=Intent.GENERATE_ITINERARY,
            message="我想去大安區咖啡廳",
            preferences=Preferences(
                district="大安區",
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["keyword"], "咖啡廳")

    async def test_planned_search_empty_falls_back_to_recommend(self) -> None:
        self.place_adapter.search_result = PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0)
        self.loop._client = StaticJSONClient(
            {
                "tool": "place_search",
                "params": {
                    "district": "大安區",
                    "internal_category": "food",
                    "keyword": "咖啡廳",
                },
            }
        )

        result = await self.loop.run(
            intent=Intent.GENERATE_ITINERARY,
            message="我想去大安區咖啡廳",
            preferences=Preferences(
                district="大安區",
                interest_tags=["cafes"],
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search", "place_recommend"])
        self.assertEqual(self.place_adapter.calls[1][1]["districts"], ["大安區"])
        self.assertEqual(self.place_adapter.calls[1][1]["internal_category"], "food")
        self.assertEqual(self.place_adapter.calls[1][1]["limit"], 5)

    async def test_planned_search_empty_and_recommend_empty_returns_no_results(self) -> None:
        self.place_adapter.search_result = PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0)
        self.place_adapter.recommend_result = PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0)
        self.loop._client = StaticJSONClient(
            {
                "tool": "place_search",
                "params": {
                    "district": "大安區",
                    "keyword": "咖啡廳",
                },
            }
        )

        result = await self.loop.run(
            intent=Intent.GENERATE_ITINERARY,
            message="我想去大安區咖啡廳",
            preferences=Preferences(
                district="大安區",
                interest_tags=["cafes"],
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "empty")
        self.assertEqual(result.summary, "no_matches")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search", "place_recommend"])

    async def test_invalid_llm_plan_falls_back_to_deterministic_chain(self) -> None:
        self.loop._client = StaticJSONClient(
            {
                "tool": "route_estimate",
                "params": {},
            }
        )

        result = await self.loop.run(
            intent=Intent.GENERATE_ITINERARY,
            message="幫我排今晚從台北車站出發的萬華區咖啡行程",
            preferences=Preferences(
                district="萬華區",
                interest_tags=["cafes"],
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][0], "place_recommend")
