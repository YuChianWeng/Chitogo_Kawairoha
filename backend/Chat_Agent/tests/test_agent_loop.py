from __future__ import annotations

import unittest

from app.chat.loop import AgentLoop
from app.chat.trace_recorder import TraceRecorder
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
        self.search_results: list[PlaceListResult] = []
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
        if self.search_results:
            return self.search_results.pop(0)
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

    async def get_vibe_tags(self, **_: object) -> object:
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

    async def _run_with_invalid_plan(
        self,
        *,
        message: str,
        preferences: Preferences,
        intent: Intent = Intent.GENERATE_ITINERARY,
        trace_recorder: TraceRecorder | None = None,
    ):
        self.loop._client = StaticJSONClient(
            {
                "tool": "route_estimate",
                "params": {},
            }
        )
        return await self.loop.run(
            intent=intent,
            message=message,
            preferences=preferences,
            trace_recorder=trace_recorder,
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

    async def test_valid_llm_plan_allows_primary_type(self) -> None:
        self.loop._client = StaticJSONClient(
            {
                "tool": "place_search",
                "params": {
                    "district": "大安區",
                    "primary_type": "museum",
                    "limit": 2,
                },
            }
        )

        result = await self.loop.run(
            intent=Intent.CHAT_GENERAL,
            message="想去博物館",
            preferences=Preferences(language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][0], "place_search")
        self.assertEqual(self.place_adapter.calls[0][1]["district"], "大安區")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "museum")
        self.assertEqual(self.place_adapter.calls[0][1]["limit"], 2)

    async def test_relax_drops_district_when_region_empty(self) -> None:
        self.place_adapter.search_results = [
            PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0),
            PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0),
            PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0),
            PlaceListResult(
                status="ok",
                items=[build_place(4, "Anywhere Ramen")],
                total=1,
                limit=5,
                offset=0,
            ),
        ]
        self.loop._client = StaticJSONClient(
            {
                "tool": "place_search",
                "params": {
                    "district": "北投區",
                },
            }
        )
        trace_recorder = TraceRecorder()

        result = await self.loop.run(
            intent=Intent.GENERATE_ITINERARY,
            message="我想找北投的拉麵",
            preferences=Preferences(
                district="北投區",
                interest_tags=["拉麵"],
                budget_level="mid",
                indoor_preference=True,
                language="zh-TW",
            ),
            trace_recorder=trace_recorder,
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search"] * 4)
        self.assertEqual(
            result.relaxations_applied,
            [
                "dropped_indoor_preference",
                "dropped_max_budget_level",
                "dropped_district",
            ],
        )
        self.assertEqual(
            result.original_filters,
            {
                "district": "北投區",
                "primary_type": "ramen_restaurant",
                "max_budget_level": 2,
                "indoor": True,
                "limit": 5,
                "offset": 0,
            },
        )
        self.assertIn("district", self.place_adapter.calls[2][1])
        self.assertNotIn("district", self.place_adapter.calls[3][1])
        trace = trace_recorder.finalize(final_status="success", outcome="ok")
        self.assertEqual([step.name for step in trace.steps], ["tool.place_search"] * 4)
        self.assertEqual(trace.steps[-1].detail.get("relaxation"), "dropped_district")

    async def test_relax_drops_primary_type_as_last_resort(self) -> None:
        self.place_adapter.search_results = [
            PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0),
            PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0),
            PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0),
            PlaceListResult(status="empty", items=[], total=0, limit=5, offset=0),
            PlaceListResult(
                status="ok",
                items=[build_place(5, "Fallback Cafe")],
                total=1,
                limit=5,
                offset=0,
            ),
        ]

        result = await self._run_with_invalid_plan(
            message="幫我找大安區咖啡店",
            preferences=Preferences(
                district="大安區",
                interest_tags=["cafes"],
                budget_level="mid",
                indoor_preference=True,
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search"] * 5)
        self.assertEqual(
            result.relaxations_applied,
            [
                "dropped_indoor_preference",
                "dropped_max_budget_level",
                "dropped_district",
                "dropped_primary_type",
            ],
        )
        self.assertEqual(self.place_adapter.calls[-1][1]["internal_category"], "food")
        self.assertEqual(self.place_adapter.calls[-1][1]["keyword"], "cafe")
        self.assertNotIn("primary_type", self.place_adapter.calls[-1][1])

    async def test_no_relaxation_needed_when_first_attempt_hits(self) -> None:
        result = await self._run_with_invalid_plan(
            message="幫我找大安區咖啡店",
            preferences=Preferences(
                district="大安區",
                interest_tags=["cafes"],
                budget_level="mid",
                indoor_preference=True,
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.relaxations_applied, [])
        self.assertEqual(
            result.original_filters,
            {
                "district": "大安區",
                "internal_category": "food",
                "primary_type": "cafe",
                "keyword": "cafe",
                "max_budget_level": 2,
                "indoor": True,
                "limit": 5,
                "offset": 0,
            },
        )
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search"])

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
        self.assertEqual(self.place_adapter.calls[0][0], "place_search")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "cafe")

    async def test_cuisine_tag_routes_to_primary_type(self) -> None:
        result = await self._run_with_invalid_plan(
            message="推薦大安區的日式餐廳",
            preferences=Preferences(
                district="大安區",
                interest_tags=["日式"],
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search"])
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "japanese_restaurant")

        self.place_adapter.calls.clear()
        result = await self._run_with_invalid_plan(
            message="推薦大安區的日式餐廳",
            preferences=Preferences(
                district="大安區",
                interest_tags=["日式餐廳"],
                language="zh-TW",
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search"])
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "japanese_restaurant")

    async def test_attraction_types_routes_to_primary_type(self) -> None:
        result = await self._run_with_invalid_plan(
            message="推薦一間博物館",
            preferences=Preferences(interest_tags=["博物館"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "museum")

        self.place_adapter.calls.clear()
        result = await self._run_with_invalid_plan(
            message="推薦一間美術館",
            preferences=Preferences(interest_tags=["美術館"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "art_gallery")

    async def test_nature_types_routes_to_primary_type(self) -> None:
        result = await self._run_with_invalid_plan(
            message="推薦一個公園",
            preferences=Preferences(interest_tags=["公園"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "park")

        self.place_adapter.calls.clear()
        result = await self._run_with_invalid_plan(
            message="推薦一條步道",
            preferences=Preferences(interest_tags=["步道"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "hiking_area")

    async def test_shopping_types_routes_to_primary_type(self) -> None:
        result = await self._run_with_invalid_plan(
            message="推薦一間百貨公司",
            preferences=Preferences(interest_tags=["百貨"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "department_store")

        self.place_adapter.calls.clear()
        result = await self._run_with_invalid_plan(
            message="推薦一個市場",
            preferences=Preferences(interest_tags=["市場"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "market")

    async def test_drink_types_routes_to_primary_type(self) -> None:
        result = await self._run_with_invalid_plan(
            message="推薦一間咖啡廳",
            preferences=Preferences(interest_tags=["咖啡廳"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "coffee_shop")

        self.place_adapter.calls.clear()
        result = await self._run_with_invalid_plan(
            message="推薦一間酒吧",
            preferences=Preferences(interest_tags=["酒吧"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "bar")

    async def test_dessert_types_routes_to_primary_type(self) -> None:
        result = await self._run_with_invalid_plan(
            message="推薦一間烘焙店",
            preferences=Preferences(interest_tags=["烘焙"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "bakery")

        self.place_adapter.calls.clear()
        result = await self._run_with_invalid_plan(
            message="推薦一間冰淇淋店",
            preferences=Preferences(interest_tags=["冰淇淋"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "ice_cream_shop")

    async def test_cafes_canonical_still_routes(self) -> None:
        result = await self._run_with_invalid_plan(
            message="推薦一間咖啡店",
            preferences=Preferences(interest_tags=["cafes"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search"])
        self.assertEqual(self.place_adapter.calls[0][1]["primary_type"], "cafe")

    async def test_temples_still_uses_category(self) -> None:
        result = await self._run_with_invalid_plan(
            message="我想找寺廟",
            preferences=Preferences(interest_tags=["temples"], language="zh-TW"),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual([call[0] for call in self.place_adapter.calls], ["place_search"])
        self.assertEqual(self.place_adapter.calls[0][1]["internal_category"], "attraction")
        self.assertEqual(self.place_adapter.calls[0][1]["keyword"], "temple")
        self.assertNotIn("primary_type", self.place_adapter.calls[0][1])
