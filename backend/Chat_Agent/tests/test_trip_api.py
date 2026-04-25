from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

try:
    import httpx  # type: ignore
except ModuleNotFoundError:
    httpx = types.ModuleType("httpx")

    class Timeout:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    class HTTPError(Exception):
        pass

    class AsyncClient:
        async def __aenter__(self) -> "AsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    httpx.Timeout = Timeout
    httpx.HTTPError = HTTPError
    httpx.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx

from app.api.v1.trip import (
    DemandRequest,
    SelectRequest,
    SetupRequest,
    get_candidates,
    place_tool_adapter,
    post_demand,
    post_select,
    post_setup,
)
from app.services import candidate_picker
from app.session.models import FlowState, Session, TransportConfig, TripCandidateCard
from app.session.store import session_store
from app.tools.models import (
    LegalLodgingListResult,
    LegalLodgingSummary,
    LodgingCandidateItem,
    LodgingCandidatesResult,
    LodgingLegalCheckResult,
    PlaceListResult,
    ToolPlace,
)


def build_request(path: str, query_string: str) -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query_string.encode("utf-8"),
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
        receive=receive,
    )


class _StubLLMClient:
    async def generate_text(self, _: str) -> str:
        return "出發吧"


class TripApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await session_store.clear()

    async def asyncTearDown(self) -> None:
        await session_store.clear()

    async def test_setup_request_rejects_transport_and_route_succeeds_without_it(self) -> None:
        session_id = str(uuid4())
        await session_store.set(Session(session_id=session_id, flow_state=FlowState.TRANSPORT))

        with self.assertRaises(ValidationError):
            SetupRequest.model_validate(
                {
                    "session_id": session_id,
                    "accommodation": {"booked": False, "district": "大安區"},
                    "transport": {"mode": "transit", "max_minutes_per_leg": 30},
                }
            )

        response = await post_setup(
            SetupRequest(
                session_id=session_id,
                accommodation={"booked": False, "district": "大安區"},
                return_time="21:00",
                return_destination="飯店",
            )
        )
        session = await session_store.get(session_id)

        self.assertTrue(response.setup_complete)
        self.assertIsNotNone(session)
        self.assertEqual(session.flow_state, FlowState.RECOMMENDING)
        self.assertIsNone(session.last_transport_config)

    async def test_setup_with_invalid_hotel_returns_recommendations_and_stays_on_setup(self) -> None:
        session_id = str(uuid4())
        await session_store.set(Session(session_id=session_id, flow_state=FlowState.TRANSPORT))

        with patch.object(
            place_tool_adapter,
            "check_lodging_legal_status",
            new=AsyncMock(
                return_value=LodgingLegalCheckResult(status="ok", is_legal=False)
            ),
        ), patch.object(
            place_tool_adapter,
            "search_lodging_candidates",
            new=AsyncMock(
                return_value=LodgingCandidatesResult(
                    status="ok",
                    items=[
                        LodgingCandidateItem(
                            name="合法旅宿A",
                            district="大安區",
                            address="台北市大安區仁愛路 1 號",
                            confidence=0.93,
                        )
                    ],
                )
            ),
        ), patch.object(
            place_tool_adapter,
            "list_legal_lodgings",
            new=AsyncMock(
                return_value=LegalLodgingListResult(
                    status="ok",
                    items=[
                        LegalLodgingSummary(
                            license_no="L-001",
                            name="合法旅宿A",
                            lodging_category="hotel",
                            district="大安區",
                            address="台北市大安區仁愛路 1 號",
                        ),
                        LegalLodgingSummary(
                            license_no="L-002",
                            name="合法旅宿B",
                            lodging_category="hotel",
                            district="大安區",
                            address="台北市大安區信義路 2 號",
                        ),
                        LegalLodgingSummary(
                            license_no="L-003",
                            name="合法旅宿C",
                            lodging_category="hotel",
                            district="中山區",
                            address="台北市中山區南京東路 3 號",
                        ),
                    ],
                )
            ),
        ):
            response = await post_setup(
                SetupRequest(
                    session_id=session_id,
                    accommodation={"booked": True, "hotel_name": "不存在飯店"},
                )
            )

        session = await session_store.get(session_id)

        self.assertFalse(response.setup_complete)
        self.assertEqual(response.accommodation_status, "not_found")
        self.assertIsNotNone(response.hotel_validation)
        self.assertEqual(
            [item["name"] for item in response.hotel_validation.alternatives],
            ["合法旅宿A"],
        )
        self.assertEqual(
            [item["name"] for item in response.hotel_validation.recommendations],
            ["合法旅宿B", "合法旅宿C"],
        )
        self.assertIsNotNone(session)
        self.assertEqual(session.flow_state, FlowState.TRANSPORT)
        self.assertIsNotNone(session.accommodation)
        self.assertEqual(session.accommodation.hotel_name, "不存在飯店")
        self.assertFalse(session.accommodation.hotel_valid)

    async def test_get_candidates_requires_transport_query(self) -> None:
        session_id = str(uuid4())
        await session_store.set(Session(session_id=session_id, flow_state=FlowState.RECOMMENDING))

        request = build_request(
            "/api/v1/trip/candidates",
            f"session_id={session_id}&lat=25.04&lng=121.5&max_minutes_per_leg=20",
        )

        with self.assertRaises(HTTPException) as exc_info:
            await get_candidates(
                request=request,
                session_id=session_id,
                lat=25.04,
                lng=121.5,
                max_minutes_per_leg=20,
            )

        self.assertEqual(exc_info.exception.status_code, 400)
        self.assertEqual(exc_info.exception.detail, "candidates_error:missing_transport_mode")

    async def test_latest_candidate_transport_is_used_for_navigation(self) -> None:
        session_id = str(uuid4())
        await session_store.set(Session(session_id=session_id, flow_state=FlowState.RECOMMENDING))

        cards = [
            TripCandidateCard(
                venue_id=101,
                name="Drive Stop",
                category="attraction",
                lat=25.04,
                lng=121.50,
                distance_min=12,
                why_recommended="近",
            )
        ]
        seen_transports: list[tuple[str, int]] = []

        async def fake_pick_candidates(
            session: Session,
            origin_lat: float,
            origin_lng: float,
            *,
            transport_config: TransportConfig,
        ) -> tuple[list[TripCandidateCard], bool, str | None]:
            seen_transports.append((transport_config.mode, transport_config.max_minutes_per_leg))
            session.last_candidate_ids = [card.venue_id for card in cards]
            return cards, False, None

        with patch("app.api.v1.trip.picker.pick_candidates", side_effect=fake_pick_candidates):
            first_request = build_request(
                "/api/v1/trip/candidates",
                f"session_id={session_id}&lat=25.04&lng=121.5&mode=walk&max_minutes_per_leg=10",
            )
            await get_candidates(
                request=first_request,
                session_id=session_id,
                lat=25.04,
                lng=121.5,
                max_minutes_per_leg=10,
            )

            second_request = build_request(
                "/api/v1/trip/candidates",
                f"session_id={session_id}&lat=25.04&lng=121.5&mode=drive&max_minutes_per_leg=25",
            )
            await get_candidates(
                request=second_request,
                session_id=session_id,
                lat=25.04,
                lng=121.5,
                max_minutes_per_leg=25,
            )

        stored = await session_store.get(session_id)
        self.assertEqual(seen_transports, [("walk", 10), ("drive", 25)])
        self.assertIsNotNone(stored)
        self.assertEqual(stored.last_transport_config.model_dump(), TransportConfig(mode="drive", max_minutes_per_leg=25).model_dump())

        with patch(
            "app.api.v1.trip.place_tool_adapter.batch_get_places",
            new=AsyncMock(return_value=PlaceListResult(status="empty", items=[], total=0)),
        ), patch("app.api.v1.trip._llm_client", return_value=_StubLLMClient()):
            response = await post_select(
                SelectRequest(
                    session_id=session_id,
                    venue_id=101,
                    current_lat=25.04,
                    current_lng=121.5,
                )
            )

        body = json.loads(response.body)
        self.assertEqual(body["navigation"]["google_maps_url"], "https://maps.google.com/?daddr=0.0,0.0&travelmode=driving")

    async def test_post_demand_uses_last_transport_context(self) -> None:
        session_id = str(uuid4())
        session = Session(
            session_id=session_id,
            flow_state=FlowState.RECOMMENDING,
            last_transport_config=TransportConfig(mode="walk", max_minutes_per_leg=15),
        )
        await session_store.set(session)

        observed: list[TransportConfig] = []

        async def fake_demand_mode(
            session: Session,
            demand_text: str,
            origin_lat: float,
            origin_lng: float,
            *,
            transport_config: TransportConfig,
        ) -> tuple[list[TripCandidateCard], str | None]:
            observed.append(transport_config)
            return (
                [
                    TripCandidateCard(
                        venue_id=202,
                        name="Alt Spot",
                        category="attraction",
                        lat=25.05,
                        lng=121.52,
                        distance_min=9,
                        why_recommended="符合需求",
                    )
                ],
                None,
            )

        with patch("app.api.v1.trip.picker.demand_mode", side_effect=fake_demand_mode):
            response = await post_demand(
                DemandRequest(
                    session_id=session_id,
                    demand_text="想找文藝一點的地方",
                    lat=25.04,
                    lng=121.5,
                )
            )

        body = json.loads(response.body)
        self.assertEqual(body["alternatives"][0]["venue_id"], 202)
        self.assertEqual(observed[0].model_dump(), TransportConfig(mode="walk", max_minutes_per_leg=15).model_dump())


class CandidatePickerDemandTests(unittest.IsolatedAsyncioTestCase):
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
        ):
            cards, fallback_reason = await candidate_picker.demand_mode(
                session,
                "找咖啡",
                25.04,
                121.5,
                transport_config=TransportConfig(mode="walk", max_minutes_per_leg=15),
            )

        self.assertEqual(fallback_reason, "only 1 alternatives found within range")
        self.assertEqual([card.venue_id for card in cards], [303])
        self.assertEqual(session.last_candidate_ids, [303])
        self.assertIsNotNone(session.reachable_cache)
        self.assertEqual(session.reachable_cache.venue_ids, [303])
