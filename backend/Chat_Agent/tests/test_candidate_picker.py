from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services import candidate_picker
from app.services.weather import WeatherContext
from app.session.models import FlowState, Session, TransportConfig
from app.tools.models import PlaceListResult, ToolPlace


def _make_place(
    venue_id: int,
    name: str,
    *,
    category: str,
    primary_type: str,
    rating: float = 4.5,
) -> ToolPlace:
    return ToolPlace(
        venue_id=venue_id,
        name=name,
        district="大安區",
        category=category,
        primary_type=primary_type,
        formatted_address=f"台北市大安區測試路 {venue_id} 號",
        rating=rating,
        user_rating_count=100,
        lat=25.04 + venue_id * 0.0001,
        lng=121.5 + venue_id * 0.0001,
    )


async def _fake_why_recommended(scored: list[tuple[object, int]], gene: str) -> list[str]:
    return [f"{gene}-推薦" for _ in scored]


class CandidatePickerTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_pick_candidates_uses_open_now_then_relaxes_it_last(self) -> None:
        session = Session(
            session_id=str(uuid4()),
            flow_state=FlowState.RECOMMENDING,
            gene_affinity_weights={"museum": 1.5},
        )
        strict_food = [
            _make_place(1, "Open Food 1", category="food", primary_type="restaurant"),
            _make_place(2, "Open Food 2", category="food", primary_type="restaurant"),
        ]
        strict_attr = [
            _make_place(3, "Open Attr 1", category="attraction", primary_type="museum"),
            _make_place(4, "Open Attr 2", category="attraction", primary_type="museum"),
        ]
        relaxed_food = strict_food + [
            _make_place(5, "Late Food 1", category="food", primary_type="restaurant"),
            _make_place(6, "Late Food 2", category="food", primary_type="restaurant"),
        ]
        relaxed_attr = strict_attr + [
            _make_place(7, "Late Attr 1", category="attraction", primary_type="museum"),
            _make_place(8, "Late Attr 2", category="attraction", primary_type="museum"),
        ]

        async def fake_search_places(**kwargs: object) -> PlaceListResult:
            internal_category = kwargs.get("internal_category")
            open_now = kwargs.get("open_now")
            if internal_category == "food" and open_now is True:
                return PlaceListResult(status="ok", items=strict_food, total=len(strict_food))
            if internal_category == "attraction" and open_now is True:
                return PlaceListResult(status="ok", items=strict_attr, total=len(strict_attr))
            if internal_category == "food":
                return PlaceListResult(status="ok", items=relaxed_food, total=len(relaxed_food))
            return PlaceListResult(status="ok", items=relaxed_attr, total=len(relaxed_attr))

        with patch(
            "app.services.candidate_picker.place_tool_adapter.search_places",
            new=AsyncMock(side_effect=fake_search_places),
        ) as mocked_search, patch(
            "app.services.candidate_picker.haversine_pre_filter",
            side_effect=lambda venues, *_args, **_kwargs: list(venues),
        ), patch(
            "app.services.candidate_picker.route_time_estimate",
            new=AsyncMock(return_value=12),
        ), patch(
            "app.services.candidate_picker._batch_why_recommended",
            new=AsyncMock(side_effect=_fake_why_recommended),
        ), patch(
            "app.services.candidate_picker.get_weather_context",
            new=AsyncMock(return_value=WeatherContext(is_raining_likely=False, rain_probability=None)),
        ):
            cards, _rain, partial, fallback_reason = await candidate_picker.pick_candidates(
                session,
                25.04,
                121.5,
                transport_config=TransportConfig(mode="walk", max_minutes_per_leg=15),
            )

        self.assertFalse(partial)
        self.assertEqual(len(cards), 6)
        self.assertEqual(sum(1 for card in cards if card.category == "restaurant"), 3)
        self.assertEqual(sum(1 for card in cards if card.category == "attraction"), 3)
        self.assertEqual(
            fallback_reason,
            "expanded_max_minutes_to_35; relaxed_gene_affinity; dropped_open_now",
        )

        kwargs_list = [call.kwargs for call in mocked_search.await_args_list]
        self.assertEqual(len(kwargs_list), 4)
        self.assertEqual(sum(1 for kwargs in kwargs_list if kwargs.get("open_now") is True), 2)
        self.assertEqual(sum(1 for kwargs in kwargs_list if kwargs.get("open_now") is None), 2)

    async def test_pick_candidates_fills_remaining_slots_from_available_category(self) -> None:
        session = Session(session_id=str(uuid4()), flow_state=FlowState.RECOMMENDING)
        restaurants = [
            _make_place(10 + idx, f"Food {idx}", category="food", primary_type="restaurant")
            for idx in range(6)
        ]
        attractions = [
            _make_place(30, "Only Attr", category="attraction", primary_type="museum")
        ]

        async def fake_search_places(**kwargs: object) -> PlaceListResult:
            internal_category = kwargs.get("internal_category")
            if internal_category == "food":
                return PlaceListResult(status="ok", items=restaurants, total=len(restaurants))
            return PlaceListResult(status="ok", items=attractions, total=len(attractions))

        with patch(
            "app.services.candidate_picker.place_tool_adapter.search_places",
            new=AsyncMock(side_effect=fake_search_places),
        ), patch(
            "app.services.candidate_picker.haversine_pre_filter",
            side_effect=lambda venues, *_args, **_kwargs: list(venues),
        ), patch(
            "app.services.candidate_picker.route_time_estimate",
            new=AsyncMock(return_value=8),
        ), patch(
            "app.services.candidate_picker._batch_why_recommended",
            new=AsyncMock(side_effect=_fake_why_recommended),
        ), patch(
            "app.services.candidate_picker.get_weather_context",
            new=AsyncMock(return_value=WeatherContext(is_raining_likely=False, rain_probability=None)),
        ):
            cards, _rain, partial, fallback_reason = await candidate_picker.pick_candidates(
                session,
                25.04,
                121.5,
                transport_config=TransportConfig(mode="walk", max_minutes_per_leg=15),
            )

        self.assertFalse(partial)
        self.assertEqual(len(cards), 6)
        self.assertEqual(sum(1 for card in cards if card.category == "restaurant"), 5)
        self.assertEqual(sum(1 for card in cards if card.category == "attraction"), 1)
        self.assertEqual(
            fallback_reason,
            "expanded_max_minutes_to_35; relaxed_gene_affinity; dropped_open_now",
        )


class CandidatePickerDemandTests(unittest.IsolatedAsyncioTestCase):
    async def test_demand_mode_relaxes_filters_before_dropping_open_now(self) -> None:
        session = Session(session_id=str(uuid4()), flow_state=FlowState.RECOMMENDING)
        cafe_only = [
            _make_place(201, "Cafe Match", category="food", primary_type="cafe")
        ]
        broad_food_open = cafe_only + [
            _make_place(202, "Food Match 2", category="food", primary_type="restaurant")
        ]
        broad_food_anytime = broad_food_open + [
            _make_place(203, "Food Match 3", category="food", primary_type="restaurant")
        ]

        async def fake_search_places(**kwargs: object) -> PlaceListResult:
            internal_category = kwargs.get("internal_category")
            primary_type = kwargs.get("primary_type")
            open_now = kwargs.get("open_now")
            if internal_category == "food" and primary_type == "cafe" and open_now is True:
                return PlaceListResult(status="ok", items=cafe_only, total=len(cafe_only))
            if internal_category == "food" and open_now is True:
                return PlaceListResult(status="ok", items=broad_food_open, total=len(broad_food_open))
            if internal_category == "food":
                return PlaceListResult(status="ok", items=broad_food_anytime, total=len(broad_food_anytime))
            return PlaceListResult(status="ok", items=[], total=0)

        with patch(
            "app.services.candidate_picker._llm_parse_demand",
            new=AsyncMock(return_value=("food", "cafe")),
        ), patch(
            "app.services.candidate_picker.place_tool_adapter.search_places",
            new=AsyncMock(side_effect=fake_search_places),
        ) as mocked_search, patch(
            "app.services.candidate_picker.haversine_pre_filter",
            side_effect=lambda venues, *_args, **_kwargs: list(venues),
        ), patch(
            "app.services.candidate_picker.route_time_estimate",
            new=AsyncMock(return_value=9),
        ), patch(
            "app.services.candidate_picker._batch_why_recommended",
            new=AsyncMock(side_effect=_fake_why_recommended),
        ), patch(
            "app.services.candidate_picker.get_weather_context",
            new=AsyncMock(return_value=WeatherContext(is_raining_likely=False, rain_probability=None)),
        ):
            cards, _rain, fallback_reason = await candidate_picker.demand_mode(
                session,
                "找咖啡",
                25.04,
                121.5,
                transport_config=TransportConfig(mode="walk", max_minutes_per_leg=15),
            )

        self.assertEqual([card.venue_id for card in cards], [201, 202, 203])
        self.assertEqual(
            fallback_reason,
            "expanded_max_minutes_to_50; relaxed_demand_filters; dropped_open_now",
        )

        kwargs_list = [call.kwargs for call in mocked_search.await_args_list]
        self.assertEqual(len(kwargs_list), 3)
        self.assertEqual(kwargs_list[0]["primary_type"], "cafe")
        self.assertEqual(kwargs_list[0]["open_now"], True)
        self.assertIsNone(kwargs_list[1].get("primary_type"))
        self.assertEqual(kwargs_list[1]["open_now"], True)
        self.assertIsNone(kwargs_list[2].get("primary_type"))
        self.assertIsNone(kwargs_list[2].get("open_now"))

    async def test_demand_mode_updates_candidate_ids_for_follow_up_selection(self) -> None:
        session = Session(session_id=str(uuid4()), flow_state=FlowState.RECOMMENDING)
        venue = ToolPlace(
            venue_id=303,
            name="Demand Cafe",
            district="大安區",
            category="food",
            primary_type="cafe",
            rating=4.8,
            lat=25.04,
            lng=121.52,
        )

        with patch(
            "app.services.candidate_picker._llm_parse_demand",
            new=AsyncMock(return_value=("food", "cafe")),
        ), patch(
            "app.services.candidate_picker.place_tool_adapter.search_places",
            new=AsyncMock(return_value=PlaceListResult(status="ok", items=[venue], total=1, limit=20, offset=0)),
        ), patch(
            "app.services.candidate_picker.haversine_pre_filter",
            return_value=[venue],
        ), patch(
            "app.services.candidate_picker.route_time_estimate",
            new=AsyncMock(return_value=8),
        ), patch(
            "app.services.candidate_picker._batch_why_recommended",
            new=AsyncMock(return_value=["近又順路"]),
        ), patch(
            "app.services.candidate_picker.get_weather_context",
            new=AsyncMock(return_value=WeatherContext(is_raining_likely=False, rain_probability=None)),
        ):
            cards, _rain, fallback_reason = await candidate_picker.demand_mode(
                session,
                "找咖啡",
                25.04,
                121.5,
                transport_config=TransportConfig(mode="walk", max_minutes_per_leg=15),
            )

        self.assertIsNotNone(fallback_reason)
        self.assertIn("partial_results", fallback_reason)
        self.assertIn("dropped_open_now", fallback_reason)
        self.assertEqual([card.venue_id for card in cards], [303])
        self.assertEqual(session.last_candidate_ids, [303])
        self.assertIsNotNone(session.reachable_cache)
        self.assertEqual(session.reachable_cache.venue_ids, [303])
