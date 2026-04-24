from __future__ import annotations

import unittest

from app.chat.itinerary_builder import ItineraryBuilder
from app.session.models import Preferences, TimeWindow
from app.tools.models import RouteResult, ToolPlace
from app.tools.registry import ToolRegistry


def build_place(venue_id: int, name: str) -> ToolPlace:
    return ToolPlace(
        venue_id=venue_id,
        name=name,
        category="food",
        district="萬華區",
        primary_type="cafe",
        lat=25.03 + (venue_id * 0.001),
        lng=121.50 + (venue_id * 0.001),
        rating=4.5,
    )


class StubPlaceAdapter:
    async def search_places(self, **_: object) -> object:
        return None

    async def recommend_places(self, **_: object) -> object:
        return None

    async def batch_get_places(self, **_: object) -> object:
        return None

    async def nearby_places(self, **_: object) -> object:
        return None

    async def get_categories(self) -> object:
        return None

    async def get_vibe_tags(self, **_: object) -> object:
        return None

    async def get_stats(self) -> object:
        return None


class StubRouteAdapter:
    def __init__(self, *, status: str = "ok") -> None:
        self.status = status
        self.calls: list[dict[str, object]] = []

    async def estimate_route(self, **kwargs: object) -> RouteResult:
        self.calls.append(kwargs)
        return RouteResult(
            distance_m=1000,
            duration_min=10,
            provider="google_maps" if self.status == "ok" else "haversine",
            status=self.status,  # type: ignore[arg-type]
            transport_mode="transit",
            estimated=self.status != "ok",
        )


class ItineraryBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_returns_structured_itinerary(self) -> None:
        route_adapter = StubRouteAdapter(status="ok")
        builder = ItineraryBuilder(
            registry=ToolRegistry(
                place_adapter=StubPlaceAdapter(),
                route_adapter=route_adapter,
            )
        )

        result = await builder.build(
            places=[
                build_place(1, "Cafe A"),
                build_place(2, "Cafe B"),
                build_place(3, "Cafe C"),
            ],
            preferences=Preferences(
                district="萬華區",
                language="zh-TW",
                time_window=TimeWindow(start_time="18:00", end_time="22:00"),
            ),
        )

        self.assertEqual(result.routing_status, "full")
        self.assertEqual(len(result.itinerary.stops), 3)
        self.assertEqual(len(result.itinerary.legs), 2)
        self.assertEqual(result.itinerary.stops[0].arrival_time, "18:00")
        self.assertGreater(result.itinerary.total_duration_min, 0)
        self.assertEqual(len(route_adapter.calls), 2)

    async def test_build_marks_partial_fallback_when_route_estimates_fallback(self) -> None:
        builder = ItineraryBuilder(
            registry=ToolRegistry(
                place_adapter=StubPlaceAdapter(),
                route_adapter=StubRouteAdapter(status="fallback"),
            )
        )

        result = await builder.build(
            places=[
                build_place(1, "Cafe A"),
                build_place(2, "Cafe B"),
            ],
            preferences=Preferences(language="en"),
        )

        self.assertEqual(result.routing_status, "partial_fallback")
        self.assertTrue(result.itinerary.legs[0].estimated)
