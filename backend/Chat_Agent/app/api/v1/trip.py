from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.gene_classifier import (
    GENE_BASE_AFFINITY,
    TravelGeneClassifier,
)
from app.services import candidate_picker as picker
from app.services import go_home_advisor
from app.services.reachability import haversine_distance
from app.session.models import (
    AccommodationConfig,
    FlowState,
    Session,
    TransportConfig,
    TripCandidateCard,
    VisitedStop,
    utc_now,
)
from app.session.store import session_store
from app.tools.place_adapter import place_tool_adapter
from app.tools.models import ToolPlace

router = APIRouter(prefix="/trip", tags=["trip"])
logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_gene_classifier = TravelGeneClassifier()
_VALID_MODES = {"walk", "transit", "drive"}
_ACCOMMODATION_MODES = {"booked", "need_hotel", "no_stay"}
_BUDGET_TO_MAX_LEVEL = {
    "budget": 1,
    "mid": 2,
    "luxury": 4,
}
_BUDGET_RANK = {
    "PRICE_LEVEL_FREE": 0,
    "INEXPENSIVE": 1,
    "MODERATE": 2,
    "EXPENSIVE": 3,
    "VERY_EXPENSIVE": 4,
}


# ─── FSM guard ────────────────────────────────────────────────────────────────

class SessionFSM:
    @staticmethod
    def assert_state(session: Session, *allowed: FlowState) -> None:
        if session.flow_state not in allowed:
            expected = allowed[0].value if len(allowed) == 1 else "_or_".join(s.value for s in allowed)
            raise ValueError(f"state_error:expected_{expected}")


# ─── Request/response schemas ─────────────────────────────────────────────────

class QuizRequest(BaseModel):
    session_id: str
    answers: dict[str, str]
    model_config = ConfigDict(extra="forbid")


class QuizResponse(BaseModel):
    session_id: str
    travel_gene: str
    mascot: str
    gene_description: str


class AccommodationInput(BaseModel):
    mode: Literal["booked", "need_hotel", "no_stay"]
    hotel_name: str | None = None
    district: str | None = None
    budget_tier: Literal["budget", "mid", "luxury"] | None = None
    model_config = ConfigDict(extra="forbid")


class SetupRequest(BaseModel):
    session_id: str
    accommodation: AccommodationInput | None = None
    return_time: str | None = None
    return_destination: str | None = None
    model_config = ConfigDict(extra="forbid")


class HotelRecommendationCard(BaseModel):
    license_no: str | None = None
    place_id: int | None = None
    name: str
    district: str | None = None
    address: str | None = None
    rating: float | None = None
    budget_level: str | None = None
    google_maps_uri: str | None = None
    confidence: float | None = None


class HotelValidationResponse(BaseModel):
    valid: bool
    matched_name: str | None
    match_type: str | None
    confidence: float | None
    district: str | None
    address: str | None
    alternatives: list[HotelRecommendationCard]
    last_updated: str


class SetupResponse(BaseModel):
    session_id: str
    accommodation_status: str
    hotel_validation: HotelValidationResponse | None
    hotel_recommendations: list[HotelRecommendationCard]
    recommendation_status: str | None
    next_step: Literal["accommodation", "setup", "trip"]
    setup_complete: bool


class SelectRequest(BaseModel):
    session_id: str
    venue_id: str | int
    current_lat: float
    current_lng: float
    model_config = ConfigDict(extra="forbid")


class RateRequest(BaseModel):
    session_id: str
    stars: int = Field(..., ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class DemandRequest(BaseModel):
    session_id: str
    demand_text: str
    lat: float
    lng: float
    model_config = ConfigDict(extra="forbid")


class SnoozeRequest(BaseModel):
    session_id: str
    model_config = ConfigDict(extra="forbid")


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_session(session_id: str) -> Session:
    session = await session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return session


async def _save_session(session: Session) -> Session:
    session.updated_at = utc_now()
    session.last_activity_at = utc_now()
    return await session_store.set(session)


def _llm_client():
    from app.llm.client import llm_client
    return llm_client


def _card_to_dict(card: TripCandidateCard) -> dict[str, Any]:
    return {
        "venue_id": card.venue_id,
        "name": card.name,
        "category": card.category,
        "primary_type": card.primary_type,
        "address": card.address,
        "lat": card.lat,
        "lng": card.lng,
        "rating": card.rating,
        "distance_min": card.distance_min,
        "why_recommended": card.why_recommended,
        "rain_note": card.rain_note,
    }


async def _geocode_return_destination(address: str) -> tuple[float | None, float | None]:
    q = address.strip()
    if not q:
        return None, None
    from app.core.config import get_settings
    settings = get_settings()
    full = q if "台北" in q or "Taipei" in q else f"{q}, 台北市, 台灣"
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": full, "key": settings.google_maps_api_key, "region": "tw"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                params=params,
                timeout=float(settings.route_service_timeout_sec),
            )
    except httpx.HTTPError:
        return None, None
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None, None
    loc = data["results"][0]["geometry"]["location"]
    la, ln = loc.get("lat"), loc.get("lng")
    if la is None or ln is None:
        return None, None
    return float(la), float(ln)


async def _apply_return_dest_coords(session: Session) -> None:
    session.return_dest_lat = None
    session.return_dest_lng = None
    if (
        session.accommodation
        and session.accommodation.hotel_lat is not None
        and session.accommodation.hotel_lng is not None
    ):
        session.return_dest_lat = float(session.accommodation.hotel_lat)
        session.return_dest_lng = float(session.accommodation.hotel_lng)
        return
    if session.return_destination and session.return_destination.strip():
        la, ln = await _geocode_return_destination(session.return_destination)
        if la is not None and ln is not None:
            session.return_dest_lat = la
            session.return_dest_lng = ln


def _resolved_return_dest(
    session: Session,
    fallback_lat: float,
    fallback_lng: float,
) -> tuple[float, float]:
    if session.return_dest_lat is not None and session.return_dest_lng is not None:
        return session.return_dest_lat, session.return_dest_lng
    if session.accommodation and session.accommodation.hotel_lat and session.accommodation.hotel_lng:
        return float(session.accommodation.hotel_lat), float(session.accommodation.hotel_lng)
    return fallback_lat, fallback_lng


def _homing_dest_coords(session: Session) -> tuple[float | None, float | None]:
    """Coordinates for return destination; None if unknown (homing off for ranking)."""
    if session.return_dest_lat is not None and session.return_dest_lng is not None:
        return session.return_dest_lat, session.return_dest_lng
    if session.accommodation and session.accommodation.hotel_lat and session.accommodation.hotel_lng:
        return float(session.accommodation.hotel_lat), float(session.accommodation.hotel_lng)
    return None, None


def _normalize_mode(mode: str | None, *, error_prefix: str) -> str:
    if not mode:
        raise HTTPException(
            status_code=400,
            detail=f"{error_prefix}:missing_transport_mode",
        )
    if mode not in _VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"{error_prefix}:invalid_transport_mode:{mode}",
        )
    return mode


def _transport_from_query(request: Request, *, max_minutes_per_leg: int) -> TransportConfig:
    mode = request.query_params.get("mode")
    legacy_modes = request.query_params.getlist("modes")
    if not legacy_modes:
        legacy_modes = request.query_params.getlist("modes[]")
    if mode is None and legacy_modes:
        if len(legacy_modes) > 1:
            raise HTTPException(
                status_code=400,
                detail="candidates_error:multiple_transport_modes_not_allowed",
            )
        mode = legacy_modes[0]

    return TransportConfig(
        mode=_normalize_mode(mode, error_prefix="candidates_error"),
        max_minutes_per_leg=max_minutes_per_leg,
    )


def _normalize_lodging_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def _budget_rank(value: str | None) -> int | None:
    if value is None:
        return None
    return _BUDGET_RANK.get(value)


def _place_lookup_key(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_exact_lodging_match(query_name: str, matched_name: str) -> bool:
    return _normalize_lodging_name(query_name) == _normalize_lodging_name(matched_name)


def _serialize_hotel_card(
    *,
    license_no: str | None,
    place_id: int | None,
    name: str,
    district: str | None,
    address: str | None,
    place: ToolPlace | None = None,
    confidence: float | None = None,
) -> HotelRecommendationCard:
    return HotelRecommendationCard(
        license_no=license_no,
        place_id=place_id,
        name=name,
        district=district or getattr(place, "district", None),
        address=address or getattr(place, "formatted_address", None),
        rating=getattr(place, "rating", None),
        budget_level=getattr(place, "budget_level", None),
        google_maps_uri=getattr(place, "google_maps_uri", None),
        confidence=confidence,
    )


async def _load_place_map(place_ids: list[int]) -> dict[int, ToolPlace]:
    unique_place_ids = list(dict.fromkeys(place_ids))
    if not unique_place_ids:
        return {}

    result = await place_tool_adapter.batch_get_places(place_ids=unique_place_ids)
    if result.status != "ok":
        return {}

    place_map: dict[int, ToolPlace] = {}
    for item in result.items:
        place_id = _place_lookup_key(item.venue_id)
        if place_id is not None:
            place_map[place_id] = item
    return place_map


def _recommendation_scope_steps(
    *,
    district: str | None,
    max_budget_level: int | None,
) -> list[tuple[str, str | None, int | None]]:
    steps: list[tuple[str, str | None, int | None]] = []
    seen: set[tuple[str | None, int | None]] = set()

    def _add(status: str, scope_district: str | None, scope_budget: int | None) -> None:
        key = (scope_district, scope_budget)
        if key in seen:
            return
        seen.add(key)
        steps.append((status, scope_district, scope_budget))

    _add("matched_preferences", district, max_budget_level)
    if max_budget_level is not None:
        _add("relaxed_budget", district, None)
    if district is not None:
        _add("expanded_citywide", None, max_budget_level)
    if district is not None or max_budget_level is not None:
        _add("expanded_citywide_and_budget", None, None)
    return steps


async def _list_recommendation_cards(
    *,
    district: str | None,
    max_budget_level: int | None,
    limit: int,
    exclude_names: set[str],
) -> list[HotelRecommendationCard]:
    lodgings = await place_tool_adapter.list_legal_lodgings(
        district=district,
        limit=100,
    )
    if lodgings.status != "ok":
        return []

    place_map = await _load_place_map(
        [item.place_id for item in lodgings.items if item.place_id is not None]
    )
    excluded = {_normalize_lodging_name(name) for name in exclude_names if name}
    ranked_rows: list[tuple[float, int, str, HotelRecommendationCard]] = []

    for item in lodgings.items:
        normalized_name = _normalize_lodging_name(item.name)
        if normalized_name in excluded:
            continue

        place = place_map.get(item.place_id) if item.place_id is not None else None
        if max_budget_level is not None:
            rank = _budget_rank(getattr(place, "budget_level", None))
            if rank is None or rank > max_budget_level:
                continue

        card = _serialize_hotel_card(
            license_no=item.license_no,
            place_id=item.place_id,
            name=item.name,
            district=item.district,
            address=item.address,
            place=place,
        )
        rating = card.rating if card.rating is not None else -1.0
        rating_count = getattr(place, "user_rating_count", 0) or 0
        ranked_rows.append((rating, rating_count, normalized_name, card))

    ranked_rows.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [row[3] for row in ranked_rows[:limit]]


async def _get_lodging_recommendations(
    *,
    district: str | None,
    budget_tier: str | None,
    limit: int,
    exclude_names: set[str],
) -> tuple[list[HotelRecommendationCard], str | None]:
    max_budget_level = _BUDGET_TO_MAX_LEVEL.get(budget_tier)
    steps = _recommendation_scope_steps(
        district=district,
        max_budget_level=max_budget_level,
    )

    for status, scope_district, scope_budget in steps:
        cards = await _list_recommendation_cards(
            district=scope_district,
            max_budget_level=scope_budget,
            limit=limit,
            exclude_names=exclude_names,
        )
        if cards:
            return cards, status

    return [], "no_results"


async def _get_candidate_cards(
    candidates: list[Any],
) -> list[HotelRecommendationCard]:
    place_map = await _load_place_map(
        [item.place_id for item in candidates if getattr(item, "place_id", None) is not None]
    )
    cards: list[HotelRecommendationCard] = []
    for item in candidates:
        place_id = getattr(item, "place_id", None)
        place = place_map.get(place_id) if place_id is not None else None
        cards.append(
            _serialize_hotel_card(
                license_no=getattr(item, "license_no", None),
                place_id=place_id,
                name=item.name,
                district=item.district,
                address=item.address,
                place=place,
                confidence=getattr(item, "confidence", None),
            )
        )
    return cards


def _store_accommodation(
    session: Session,
    *,
    mode: Literal["booked", "need_hotel", "no_stay"],
    booked: bool,
    hotel_name: str | None = None,
    hotel_valid: bool | None = None,
    matched_name: str | None = None,
    district: str | None = None,
    budget_tier: str | None = None,
    place: ToolPlace | None = None,
) -> None:
    session.accommodation = AccommodationConfig(
        mode=mode,
        booked=booked,
        hotel_name=hotel_name,
        hotel_lat=getattr(place, "lat", None),
        hotel_lng=getattr(place, "lng", None),
        hotel_valid=hotel_valid,
        matched_name=matched_name,
        district=district,
        budget_tier=budget_tier,
    )


async def _validate_lodging_selection(
    *,
    lodging_name: str,
    budget_tier: str | None = None,
) -> tuple[HotelValidationResponse, list[HotelRecommendationCard], str | None, ToolPlace | None, str]:
    try:
        legal = await place_tool_adapter.check_lodging_legal_status(name=lodging_name)
        candidates = await place_tool_adapter.search_lodging_candidates(name=lodging_name, limit=3)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="candidates_error:data_service_unavailable") from exc

    if legal.status != "ok":
        raise HTTPException(status_code=503, detail="candidates_error:data_service_unavailable")

    alternatives = await _get_candidate_cards(candidates.items if candidates.status == "ok" else [])

    if legal.is_legal and legal.lodging:
        matched_name = legal.lodging.name
        exact_match = _is_exact_lodging_match(lodging_name, matched_name)
        matched_place = None
        if legal.lodging.place_id is not None:
            place_map = await _load_place_map([legal.lodging.place_id])
            matched_place = place_map.get(legal.lodging.place_id)
        hotel_validation = HotelValidationResponse(
            valid=True,
            matched_name=matched_name,
            match_type="exact" if exact_match else "fuzzy",
            confidence=1.0 if exact_match else legal.confidence,
            district=legal.lodging.district,
            address=legal.lodging.address,
            alternatives=[],
            last_updated=str(datetime.now(UTC).date()),
        )
        return hotel_validation, [], None, matched_place, ("validated" if exact_match else "fuzzy_match")

    preferred_district = next(
        (item.district for item in alternatives if item.district),
        None,
    )
    recommendations, recommendation_status = await _get_lodging_recommendations(
        district=preferred_district,
        budget_tier=budget_tier,
        limit=3,
        exclude_names={
            lodging_name,
            *(item.name for item in alternatives),
        },
    )
    hotel_validation = HotelValidationResponse(
        valid=False,
        matched_name=None,
        match_type=None,
        confidence=None,
        district=None,
        address=None,
        alternatives=alternatives,
        last_updated=str(datetime.now(UTC).date()),
    )
    return hotel_validation, recommendations, recommendation_status, None, "not_found"


# ─── POST /quiz ───────────────────────────────────────────────────────────────

@router.post("/quiz", response_model=QuizResponse)
async def post_quiz(payload: QuizRequest) -> QuizResponse:
    session = await _get_session(payload.session_id)
    try:
        SessionFSM.assert_state(session, FlowState.QUIZ)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    answers = payload.answers

    # Validate all 9 answers
    required_keys = [f"Q{i}" for i in range(1, 10)]
    for k in required_keys:
        if k not in answers:
            raise HTTPException(status_code=400, detail="quiz_error:missing_answers")

    for k, v in answers.items():
        if k == "Q1" and v not in {"A", "B", "C"}:
            raise HTTPException(status_code=400, detail=f"quiz_error:invalid_answer:{k}")
        elif k != "Q1" and v not in {"A", "B"}:
            raise HTTPException(status_code=400, detail=f"quiz_error:invalid_answer:{k}")

    gene, mascot, description = _gene_classifier.classify(answers)

    session.quiz_answers = dict(answers)
    session.travel_gene = gene
    session.mascot = mascot
    session.gene_affinity_weights = dict(GENE_BASE_AFFINITY.get(gene, {}))
    session.flow_state = FlowState.TRANSPORT

    await _save_session(session)

    return QuizResponse(
        session_id=session.session_id,
        travel_gene=gene,
        mascot=mascot,
        gene_description=description,
    )


# ─── POST /setup ──────────────────────────────────────────────────────────────

@router.post("/setup", response_model=SetupResponse)
async def post_setup(payload: SetupRequest) -> SetupResponse:
    session = await _get_session(payload.session_id)
    try:
        SessionFSM.assert_state(session, FlowState.TRANSPORT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    hotel_validation: HotelValidationResponse | None = None
    hotel_recommendations: list[HotelRecommendationCard] = []
    recommendation_status: str | None = None
    accommodation_status = "not_required"
    next_step: Literal["accommodation", "setup", "trip"] = "accommodation"
    setup_complete = False

    if payload.accommodation is not None:
        acc = payload.accommodation
        if acc.mode not in _ACCOMMODATION_MODES:
            raise HTTPException(status_code=400, detail="setup_error:invalid_accommodation_mode")

        if acc.mode == "booked":
            if not acc.hotel_name:
                raise HTTPException(status_code=400, detail="setup_error:hotel_name_required")

            hotel_validation, hotel_recommendations, recommendation_status, matched_place, accommodation_status = (
                await _validate_lodging_selection(
                    lodging_name=acc.hotel_name,
                    budget_tier=acc.budget_tier,
                )
            )
            if hotel_validation.valid:
                _store_accommodation(
                    session,
                    mode="booked",
                    booked=True,
                    hotel_name=hotel_validation.matched_name,
                    hotel_valid=True,
                    matched_name=hotel_validation.matched_name,
                    district=hotel_validation.district,
                    place=matched_place,
                )
                next_step = "setup"
            else:
                _store_accommodation(
                    session,
                    mode="booked",
                    booked=True,
                    hotel_name=acc.hotel_name,
                    hotel_valid=False,
                    matched_name=None,
                )
                next_step = "accommodation"

        elif acc.mode == "need_hotel":
            if acc.hotel_name:
                hotel_validation, hotel_recommendations, recommendation_status, matched_place, accommodation_status = (
                    await _validate_lodging_selection(
                        lodging_name=acc.hotel_name,
                        budget_tier=acc.budget_tier,
                    )
                )
                if hotel_validation.valid:
                    _store_accommodation(
                        session,
                        mode="need_hotel",
                        booked=True,
                        hotel_name=hotel_validation.matched_name,
                        hotel_valid=True,
                        matched_name=hotel_validation.matched_name,
                        district=hotel_validation.district or acc.district,
                        budget_tier=acc.budget_tier,
                        place=matched_place,
                    )
                    next_step = "setup"
                else:
                    _store_accommodation(
                        session,
                        mode="need_hotel",
                        booked=False,
                        hotel_name=acc.hotel_name,
                        hotel_valid=False,
                        district=acc.district,
                        budget_tier=acc.budget_tier,
                    )
                    next_step = "accommodation"
            else:
                hotel_recommendations, recommendation_status = await _get_lodging_recommendations(
                    district=acc.district,
                    budget_tier=acc.budget_tier,
                    limit=3,
                    exclude_names=set(),
                )
                accommodation_status = "recommending"
                _store_accommodation(
                    session,
                    mode="need_hotel",
                    booked=False,
                    district=acc.district,
                    budget_tier=acc.budget_tier,
                )
                next_step = "accommodation"

        else:
            _store_accommodation(
                session,
                mode="no_stay",
                booked=False,
            )
            next_step = "setup"

        if payload.return_time:
            if not _TIME_RE.fullmatch(payload.return_time):
                raise HTTPException(status_code=400, detail="setup_error:invalid_return_time")
            session.return_time = payload.return_time

        if payload.return_destination:
            session.return_destination = payload.return_destination

        session.flow_state = FlowState.TRANSPORT
    else:
        if session.accommodation is None:
            raise HTTPException(status_code=400, detail="setup_error:accommodation_required")
        if (
            session.accommodation.mode != "no_stay"
            and session.accommodation.hotel_valid is not True
        ):
            raise HTTPException(status_code=400, detail="setup_error:accommodation_incomplete")

        if payload.return_time:
            if not _TIME_RE.fullmatch(payload.return_time):
                raise HTTPException(status_code=400, detail="setup_error:invalid_return_time")
            session.return_time = payload.return_time

        if payload.return_destination:
            session.return_destination = payload.return_destination

        session.flow_state = FlowState.RECOMMENDING
        next_step = "trip"
        setup_complete = True

    await _apply_return_dest_coords(session)
    await _save_session(session)

    return SetupResponse(
        session_id=session.session_id,
        accommodation_status=accommodation_status,
        hotel_validation=hotel_validation,
        hotel_recommendations=hotel_recommendations,
        recommendation_status=recommendation_status,
        next_step=next_step,
        setup_complete=setup_complete,
    )


# ─── GET /candidates ──────────────────────────────────────────────────────────

@router.get("/candidates")
async def get_candidates(
    request: Request,
    session_id: str = Query(...),
    lat: float = Query(...),
    lng: float = Query(...),
    max_minutes_per_leg: int = Query(..., ge=1, le=120),
    sim_time: str | None = Query(None, description="Demo only: HH:MM simulated Taipei time"),
) -> JSONResponse:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(status_code=400, detail="candidates_error:invalid_coordinates")

    session = await _get_session(session_id)
    try:
        SessionFSM.assert_state(session, FlowState.RECOMMENDING)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    transport_config = _transport_from_query(
        request,
        max_minutes_per_leg=max_minutes_per_leg,
    )

    now_override = go_home_advisor.parse_sim_time(sim_time)
    urgency = go_home_advisor.time_urgency(session, now_override)
    h_lat, h_lng = _homing_dest_coords(session)
    homing_active = h_lat is not None and h_lng is not None and urgency > 0.0
    urgency_level = go_home_advisor.urgency_level(urgency)

    try:
        cards, rain_cards, partial, fallback_reason = await picker.pick_candidates(
            session,
            lat,
            lng,
            transport_config=transport_config,
            urgency=urgency,
            dest_lat=h_lat,
            dest_lng=h_lng,
        )
    except ValueError as exc:
        detail = str(exc)
        if "data_service_unavailable" in detail:
            raise HTTPException(status_code=503, detail="candidates_error:data_service_unavailable") from exc
        raise HTTPException(status_code=400, detail=detail) from exc

    session.last_transport_config = transport_config

    # Persist updated session (reachable_cache + last_candidate_ids updated in picker)
    await _save_session(session)

    # Check for go-home reminder
    go_home_reminder = None
    if session.return_time:
        dest_lat, dest_lng = _resolved_return_dest(session, lat, lng)

        dist_km = haversine_distance(lat, lng, dest_lat, dest_lng)
        transit_min = max(1, int(dist_km / 12.0 * 60))

        # Proactive reminder (banner/message)
        if go_home_advisor.should_remind(session, transit_min, now_override):
            go_home_reminder = f"距離回程的時間快到了（預計 {session.return_time}）"

        # Candidate card visibility
        if go_home_advisor.is_in_window(session, now_override):
            # Add a Go Home card
            go_home_card = TripCandidateCard(
                venue_id="GO_HOME",
                name="回家去 (飯店/車站)",
                category="go_home",
                address="回程目的地",
                lat=dest_lat,
                lng=dest_lng,
                distance_min=transit_min,
                why_recommended="時間差不多囉，該準備回程了。",
            )
            cards.insert(0, go_home_card)

    restaurants = [c for c in cards if c.category == "restaurant"]
    attractions = [c for c in cards if c.category == "attraction"]

    return JSONResponse({
        "session_id": session_id,
        "candidates": [_card_to_dict(c) for c in cards],
        "rain_filtered": [_card_to_dict(c) for c in rain_cards],
        "partial": partial,
        "fallback_reason": fallback_reason,
        "restaurant_count": len(restaurants),
        "attraction_count": len(attractions),
        "go_home_reminder": go_home_reminder,
        "homing_active": homing_active,
        "urgency_level": urgency_level,
    })


# ─── POST /select ─────────────────────────────────────────────────────────────

@router.post("/select")
async def post_select(payload: SelectRequest) -> JSONResponse:
    session = await _get_session(payload.session_id)
    try:
        SessionFSM.assert_state(session, FlowState.RECOMMENDING)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Check venue is in last candidate set or is special GO_HOME
    venue_id_str = str(payload.venue_id)
    candidate_ids = [str(cid) for cid in session.last_candidate_ids]

    is_go_home = venue_id_str == "GO_HOME"

    # Allow chat-originated candidates (not in last_candidate_ids) — the data-service
    # lookup below validates the venue exists, so no hard rejection here.
    if not is_go_home and venue_id_str not in candidate_ids:
        logger.info("venue %s not in last_candidate_ids; proceeding via data-service lookup", venue_id_str)

    # Use default transport when none is set (e.g. first selection from a chat card).
    transport_config = session.last_transport_config or TransportConfig()

    # Find the candidate from the reachable cache (rebuild minimal card from last known data)
    # We need to fetch the venue details from the Data Service
    card: TripCandidateCard | None = None
    if is_go_home:
        dest_lat, dest_lng = payload.current_lat, payload.current_lng
        if session.accommodation and session.accommodation.hotel_lat and session.accommodation.hotel_lng:
            dest_lat = session.accommodation.hotel_lat
            dest_lng = session.accommodation.hotel_lng
        
        card = TripCandidateCard(
            venue_id="GO_HOME",
            name="回家去 (飯店/車站)",
            category="go_home",
            address="回程目的地",
            lat=dest_lat,
            lng=dest_lng,
            distance_min=0,
            why_recommended="辛苦了，準備回程吧！",
        )
    else:
        try:
            result = await place_tool_adapter.batch_get_places(
                place_ids=[int(payload.venue_id)] if str(payload.venue_id).isdigit() else []
            )
            if result.items:
                v = result.items[0]
                card = TripCandidateCard(
                    venue_id=v.venue_id,
                    name=v.name,
                    category="restaurant" if _is_food(v) else "attraction",
                    primary_type=getattr(v, "primary_type", None),
                    address=getattr(v, "formatted_address", None),
                    lat=v.lat or 0.0,
                    lng=v.lng or 0.0,
                    rating=getattr(v, "rating", None),
                    distance_min=0,
                    why_recommended="",
                )
        except Exception:
            pass

    if card is None:
        # Fallback: minimal card from payload
        card = TripCandidateCard(
            venue_id=payload.venue_id,
            name=str(payload.venue_id),
            category="attraction",
            lat=0.0,
            lng=0.0,
            distance_min=0,
            why_recommended="",
        )

    session.pending_venue = card

    # Build navigation URLs
    primary_mode = transport_config.mode
    google_mode = {"walk": "walking", "transit": "transit", "drive": "driving"}.get(primary_mode, "transit")
    google_url = f"https://maps.google.com/?daddr={card.lat},{card.lng}&travelmode={google_mode}"
    apple_url = f"maps://maps.apple.com/?daddr={card.lat},{card.lng}"

    # Estimate travel time
    from app.services.reachability import _haversine_minutes
    est_min = _haversine_minutes(card, payload.current_lat, payload.current_lng, primary_mode)

    # LLM encouragement message
    encouragement = f"加油！{card.name}等著你！"
    try:
        gene = session.travel_gene or "旅人"
        prompt = (
            f"你是台北旅遊嚮導。使用者的旅遊基因是「{gene}」，正前往「{card.name}」。"
            "請用繁體中文寫1-2句鼓勵的話（30字以內）。"
        )
        encouragement = await _llm_client().generate_text(prompt)
        encouragement = encouragement.strip()[:100]
    except Exception as exc:
        logger.warning("encouragement LLM failed: %s", exc)

    session.flow_state = FlowState.RATING
    await _save_session(session)

    return JSONResponse({
        "session_id": payload.session_id,
        "venue": {
            "venue_id": card.venue_id,
            "name": card.name,
            "category": card.category,
            "address": card.address,
            "lat": card.lat,
            "lng": card.lng,
        },
        "navigation": {
            "google_maps_url": google_url,
            "apple_maps_url": apple_url,
            "estimated_travel_min": est_min,
            "transport_mode": primary_mode,
        },
        "encouragement_message": encouragement,
    })


# ─── POST /rate ───────────────────────────────────────────────────────────────

@router.post("/rate")
async def post_rate(payload: RateRequest) -> JSONResponse:
    session = await _get_session(payload.session_id)
    try:
        SessionFSM.assert_state(session, FlowState.RATING)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not session.pending_venue:
        raise HTTPException(status_code=400, detail="rate_error:no_pending_venue")

    venue = session.pending_venue
    stop = VisitedStop(
        venue_id=venue.venue_id,
        venue_name=venue.name,
        category=venue.category,
        primary_type=venue.primary_type,
        address=venue.address,
        lat=venue.lat,
        lng=venue.lng,
        arrived_at=utc_now(),
        star_rating=payload.stars,
        tags=list(payload.tags),
    )
    session.visited_stops.append(stop)

    # Update affinity weights
    adjustment = 0.0
    if payload.stars == 5:
        adjustment = 0.2
    elif payload.stars <= 2:
        adjustment = -0.3

    category = venue.primary_type or venue.category
    affinity_update = {"category": category, "adjustment": adjustment}

    if adjustment != 0.0 and category:
        current = session.gene_affinity_weights.get(category, 1.0)
        session.gene_affinity_weights[category] = max(0.0, current + adjustment)

    session.pending_venue = None
    session.flow_state = FlowState.RECOMMENDING

    await _save_session(session)

    return JSONResponse({
        "session_id": payload.session_id,
        "visit_recorded": True,
        "stop_number": len(session.visited_stops),
        "affinity_update": affinity_update,
    })


# ─── POST /demand ─────────────────────────────────────────────────────────────

@router.post("/demand")
async def post_demand(payload: DemandRequest) -> JSONResponse:
    session = await _get_session(payload.session_id)
    try:
        SessionFSM.assert_state(session, FlowState.RECOMMENDING)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not payload.demand_text or not payload.demand_text.strip():
        raise HTTPException(status_code=400, detail="demand_error:empty_text")
    if session.last_transport_config is None:
        raise HTTPException(status_code=400, detail="demand_error:missing_transport_context")

    try:
        cards, rain_cards, fallback_reason = await picker.demand_mode(
            session,
            payload.demand_text,
            payload.lat,
            payload.lng,
            transport_config=session.last_transport_config,
        )
    except ValueError as exc:
        detail = str(exc)
        if "data_service_unavailable" in detail:
            raise HTTPException(status_code=503, detail="candidates_error:data_service_unavailable") from exc
        raise HTTPException(status_code=400, detail=detail) from exc

    await _save_session(session)

    return JSONResponse({
        "session_id": payload.session_id,
        "alternatives": [_card_to_dict(c) for c in cards],
        "rain_filtered": [_card_to_dict(c) for c in rain_cards],
        "fallback_reason": fallback_reason,
    })


# ─── GET /should_go_home ──────────────────────────────────────────────────────

@router.get("/should_go_home")
async def get_should_go_home(
    session_id: str = Query(...),
    lat: float = Query(...),
    lng: float = Query(...),
    sim_time: str | None = Query(None, description="Demo only: HH:MM simulated Taipei time"),
) -> JSONResponse:
    session = await _get_session(session_id)
    try:
        SessionFSM.assert_state(session, FlowState.RECOMMENDING, FlowState.RATING)
    except ValueError:
        raise HTTPException(status_code=400, detail="state_error:not_in_trip")

    if not session.return_time:
        return JSONResponse({
            "session_id": session_id,
            "remind": False,
            "message": None,
            "time_remaining_min": None,
        })

    now_override = go_home_advisor.parse_sim_time(sim_time)

    # Estimate transit time to return destination using haversine
    dest_lat, dest_lng = lat, lng  # fallback: use current location
    if session.accommodation and session.accommodation.hotel_lat and session.accommodation.hotel_lng:
        dest_lat = session.accommodation.hotel_lat
        dest_lng = session.accommodation.hotel_lng

    dist_km = haversine_distance(lat, lng, dest_lat, dest_lng)
    transit_min = max(1, int(dist_km / 12.0 * 60))  # transit ~12 km/h

    should = go_home_advisor.should_remind(session, transit_min, now_override)

    if should:
        go_home_advisor.record_reminded(session)
        await _save_session(session)

        from zoneinfo import ZoneInfo
        taipei_tz = ZoneInfo("Asia/Taipei")

        hh, mm = map(int, session.return_time.split(":"))
        now_taipei = go_home_advisor._now_taipei(now_override)
        return_dt = now_taipei.replace(hour=hh, minute=mm, second=0, microsecond=0)

        time_remaining = max(0, int((return_dt - now_taipei).total_seconds() / 60))

        return JSONResponse({
            "session_id": session_id,
            "remind": True,
            "message": f"該回家啦！距離回程的時間還有 {time_remaining} 分鐘，現在出發剛好！",
            "time_remaining_min": time_remaining,
        })

    return JSONResponse({
        "session_id": session_id,
        "remind": False,
        "message": None,
        "time_remaining_min": None,
    })


@router.post("/snooze")
async def post_snooze(payload: SnoozeRequest) -> JSONResponse:
    session = await _get_session(payload.session_id)
    go_home_advisor.snooze(session)
    await _save_session(session)
    return JSONResponse({"session_id": payload.session_id, "snoozed": True})


# ─── GET /summary ─────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(session_id: str = Query(...)) -> JSONResponse:
    session = await _get_session(session_id)
    try:
        SessionFSM.assert_state(
            session, FlowState.RECOMMENDING, FlowState.RATING, FlowState.ENDED
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="state_error:trip_not_started")

    if session.flow_state != FlowState.ENDED:
        session.flow_state = FlowState.ENDED
        await _save_session(session)

    stops = session.visited_stops
    total_stops = len(stops)

    total_elapsed = 0
    if stops:
        total_elapsed = int((stops[-1].arrived_at - session.created_at).total_seconds() / 60)

    total_dist = 0
    for i in range(1, len(stops)):
        total_dist += int(
            haversine_distance(stops[i - 1].lat, stops[i - 1].lng, stops[i].lat, stops[i].lng) * 1000
        )

    # LLM farewell
    gene = session.travel_gene or "旅人"
    mascot = session.mascot or "tourist_owl"
    farewell = f"感謝你今天的台北之旅！希望你玩得盡興！"
    try:
        stop_names = "、".join(s.venue_name for s in stops) if stops else "無"
        prompt = (
            f"你是台北旅遊嚮導。使用者的旅遊基因是「{gene}」，今天去了：{stop_names}。"
            "請用繁體中文寫一段溫馨告別語（50字以內），鼓勵使用者下次再來。"
        )
        farewell = await _llm_client().generate_text(prompt)
        farewell = farewell.strip()[:200]
    except Exception as exc:
        logger.warning("farewell LLM failed: %s", exc)

    stops_data = [
        {
            "stop_number": i + 1,
            "venue_id": s.venue_id,
            "venue_name": s.venue_name,
            "category": s.category,
            "address": s.address,
            "arrived_at": s.arrived_at.isoformat(),
            "star_rating": s.star_rating,
            "tags": s.tags,
        }
        for i, s in enumerate(stops)
    ]

    return JSONResponse({
        "session_id": session_id,
        "travel_gene": gene,
        "mascot": mascot,
        "stops": stops_data,
        "total_stops": total_stops,
        "total_elapsed_min": total_elapsed,
        "total_distance_m": total_dist,
        "mascot_farewell": farewell,
    })


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_food(venue: Any) -> bool:
    cat = (
        getattr(venue, "category", None) or
        getattr(venue, "source_category", None) or
        ""
    ).lower()
    return cat in {"food", "restaurant", "cafe", "bar", "nightmarket"}
