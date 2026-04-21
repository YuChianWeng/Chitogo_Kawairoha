from __future__ import annotations

import unittest

from app.chat.itinerary_builder import ItineraryBuilder
from app.chat.replanner import Replanner
from app.session.models import Itinerary, Leg, Preferences, Stop
from app.tools.models import RouteResult, ToolPlace
from app.tools.registry import ToolRegistry


def build_stop(index: int, venue_id: int, name: str) -> Stop:
    return Stop(
        stop_index=index,
        venue_id=venue_id,
        venue_name=name,
        category="food",
        arrival_time=f"1{index}:00",
        visit_duration_min=60,
        lat=25.03 + (venue_id * 0.001),
        lng=121.50 + (venue_id * 0.001),
    )


def build_itinerary() -> Itinerary:
    stops = [
        build_stop(0, 1, "Cafe A"),
        build_stop(1, 2, "Cafe B"),
        build_stop(2, 3, "Cafe C"),
    ]
    legs = [
        Leg(from_stop=0, to_stop=1, transit_method="transit", duration_min=10, estimated=False),
        Leg(from_stop=1, to_stop=2, transit_method="transit", duration_min=12, estimated=False),
    ]
    return Itinerary(
        summary="3-stop itinerary around 萬華區",
        total_duration_min=202,
        stops=stops,
        legs=legs,
    )


def build_place(venue_id: int, name: str) -> ToolPlace:
    return ToolPlace(
        venue_id=venue_id,
        name=name,
        category="food",
        district="萬華區",
        primary_type="cafe",
        lat=25.03 + (venue_id * 0.001),
        lng=121.50 + (venue_id * 0.001),
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

    async def get_stats(self) -> object:
        return None


class StubRouteAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def estimate_route(self, **kwargs: object) -> RouteResult:
        self.calls.append(kwargs)
        return RouteResult(
            distance_m=900,
            duration_min=9,
            provider="google_maps",
            status="ok",
            transport_mode="transit",
            estimated=False,
        )


class ReplannerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.route_adapter = StubRouteAdapter()
        self.replanner = Replanner(
            itinerary_builder=ItineraryBuilder(
                registry=ToolRegistry(
                    place_adapter=StubPlaceAdapter(),
                    route_adapter=self.route_adapter,
                )
            )
        )

    async def test_replace_preserves_untouched_stops_and_legs(self) -> None:
        itinerary = build_itinerary()
        request = self.replanner.parse_request("換掉第二站", itinerary)

        result = await self.replanner.apply(
            current_itinerary=itinerary,
            request=request,
            preferences=Preferences(language="zh-TW"),
            replacement_place=build_place(9, "Cafe Z"),
        )

        self.assertEqual(result.itinerary.stops[0].model_dump(), itinerary.stops[0].model_dump())
        self.assertNotEqual(result.itinerary.stops[1].venue_id, itinerary.stops[1].venue_id)
        self.assertEqual(result.itinerary.stops[2].venue_id, itinerary.stops[2].venue_id)
        self.assertEqual(result.itinerary.stops[2].venue_name, itinerary.stops[2].venue_name)
        self.assertEqual(len(self.route_adapter.calls), 2)

    async def test_insert_and_remove_keep_dense_ordering(self) -> None:
        itinerary = build_itinerary()

        insert_request = self.replanner.parse_request("在第二站後面加一個咖啡廳", itinerary)
        inserted = await self.replanner.apply(
            current_itinerary=itinerary,
            request=insert_request,
            preferences=Preferences(language="zh-TW"),
            replacement_place=build_place(10, "Inserted Cafe"),
        )
        remove_request = self.replanner.parse_request("刪掉最後一站", inserted.itinerary)
        removed = await self.replanner.apply(
            current_itinerary=inserted.itinerary,
            request=remove_request,
            preferences=Preferences(language="zh-TW"),
        )

        self.assertEqual(
            [stop.stop_index for stop in inserted.itinerary.stops],
            list(range(len(inserted.itinerary.stops))),
        )
        self.assertEqual(
            [leg.from_stop for leg in inserted.itinerary.legs],
            list(range(len(inserted.itinerary.stops) - 1)),
        )
        self.assertEqual(
            [stop.stop_index for stop in removed.itinerary.stops],
            list(range(len(removed.itinerary.stops))),
        )
        self.assertEqual(len(removed.itinerary.legs), len(removed.itinerary.stops) - 1)

    async def test_remove_recomputes_arrival_times_for_downstream_stops(self) -> None:
        itinerary = build_itinerary()
        request = self.replanner.parse_request("刪掉第一站", itinerary)

        result = await self.replanner.apply(
            current_itinerary=itinerary,
            request=request,
            preferences=Preferences(language="zh-TW"),
        )

        self.assertEqual(
            [stop.arrival_time for stop in result.itinerary.stops],
            ["10:00", "11:12"],
        )
        self.assertEqual(
            [stop.venue_id for stop in result.itinerary.stops],
            [2, 3],
        )

    async def test_insert_recomputes_arrival_times_for_later_stops(self) -> None:
        itinerary = build_itinerary()
        request = self.replanner.parse_request("在第二站後面加一個咖啡廳", itinerary)

        result = await self.replanner.apply(
            current_itinerary=itinerary,
            request=request,
            preferences=Preferences(language="zh-TW"),
            replacement_place=build_place(10, "Inserted Cafe"),
        )

        self.assertEqual(
            [stop.arrival_time for stop in result.itinerary.stops],
            ["10:00", "11:10", "12:19", "13:43"],
        )
        self.assertEqual(result.itinerary.stops[3].venue_id, 3)
