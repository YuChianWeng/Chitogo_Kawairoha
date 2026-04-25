from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

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

router = APIRouter(prefix="/trip", tags=["trip"])
logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_gene_classifier = TravelGeneClassifier()
_VALID_MODES = {"walk", "transit", "drive"}


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
    booked: bool
    hotel_name: str | None = None
    district: str | None = None
    budget_tier: str | None = None
    model_config = ConfigDict(extra="forbid")


class TransportInput(BaseModel):
    modes: list[str]
    max_minutes_per_leg: int = Field(30, ge=1, le=120)
    model_config = ConfigDict(extra="forbid")


class SetupRequest(BaseModel):
    session_id: str
    accommodation: AccommodationInput
    return_time: str | None = None
    return_destination: str | None = None
    transport: TransportInput
    model_config = ConfigDict(extra="forbid")


class HotelValidationResponse(BaseModel):
    valid: bool
    matched_name: str | None
    match_type: str | None
    confidence: float | None
    district: str | None
    address: str | None
    alternatives: list[dict[str, Any]]
    last_updated: str


class SetupResponse(BaseModel):
    session_id: str
    accommodation_status: str
    hotel_validation: HotelValidationResponse | None
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
    }


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

    acc = payload.accommodation
    hotel_validation: HotelValidationResponse | None = None
    accommodation_status = "not_required"

    if acc.booked:
        if not acc.hotel_name:
            raise HTTPException(status_code=400, detail="setup_error:hotel_name_required")

        # Call Data Service for hotel validation
        try:
            legal = await place_tool_adapter.check_lodging_legal_status(name=acc.hotel_name)
            candidates = await place_tool_adapter.search_lodging_candidates(name=acc.hotel_name, limit=3)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="candidates_error:data_service_unavailable") from exc

        alternatives: list[dict[str, Any]] = []
        if candidates.status == "ok" and candidates.items:
            alternatives = [
                {
                    "name": item.name,
                    "district": item.district,
                    "address": item.address,
                    "confidence": item.confidence,
                }
                for item in candidates.items
            ]

        if legal.status == "ok" and legal.is_legal and legal.lodging:
            lodging = legal.lodging
            accommodation_status = "validated" if legal.match_type == "exact" else "fuzzy_match"
            hotel_validation = HotelValidationResponse(
                valid=True,
                matched_name=lodging.name,
                match_type=legal.match_type,
                confidence=legal.confidence,
                district=lodging.district,
                address=lodging.address,
                alternatives=[],
                last_updated=str(datetime.now(UTC).date()),
            )
        else:
            accommodation_status = "not_found"
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

        session.accommodation = AccommodationConfig(
            booked=True,
            hotel_name=acc.hotel_name,
            hotel_valid=hotel_validation.valid,
            matched_name=hotel_validation.matched_name,
        )
    else:
        session.accommodation = AccommodationConfig(
            booked=False,
            district=acc.district,
            budget_tier=acc.budget_tier,
        )

    if payload.return_time:
        if not _TIME_RE.fullmatch(payload.return_time):
            raise HTTPException(status_code=400, detail="setup_error:invalid_return_time")
        session.return_time = payload.return_time

    if payload.return_destination:
        session.return_destination = payload.return_destination

    transport = payload.transport
    if not transport.modes:
        raise HTTPException(status_code=400, detail="setup_error:empty_transport_modes")
    for m in transport.modes:
        if m not in _VALID_MODES:
            raise HTTPException(status_code=400, detail=f"setup_error:invalid_transport_mode:{m}")

    session.transport_config = TransportConfig(
        modes=list(transport.modes),
        max_minutes_per_leg=transport.max_minutes_per_leg,
    )
    session.flow_state = FlowState.RECOMMENDING

    await _save_session(session)

    return SetupResponse(
        session_id=session.session_id,
        accommodation_status=accommodation_status,
        hotel_validation=hotel_validation,
        setup_complete=True,
    )


# ─── GET /candidates ──────────────────────────────────────────────────────────

@router.get("/candidates")
async def get_candidates(
    session_id: str = Query(...),
    lat: float = Query(...),
    lng: float = Query(...),
) -> JSONResponse:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(status_code=400, detail="candidates_error:invalid_coordinates")

    session = await _get_session(session_id)
    try:
        SessionFSM.assert_state(session, FlowState.RECOMMENDING)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        cards, partial, fallback_reason = await picker.pick_candidates(session, lat, lng)
    except ValueError as exc:
        detail = str(exc)
        if "data_service_unavailable" in detail:
            raise HTTPException(status_code=503, detail="candidates_error:data_service_unavailable") from exc
        raise HTTPException(status_code=400, detail=detail) from exc

    # Persist updated session (reachable_cache + last_candidate_ids updated in picker)
    await _save_session(session)

    restaurants = [c for c in cards if c.category == "restaurant"]
    attractions = [c for c in cards if c.category == "attraction"]

    return JSONResponse({
        "session_id": session_id,
        "candidates": [_card_to_dict(c) for c in cards],
        "partial": partial,
        "fallback_reason": fallback_reason,
        "restaurant_count": len(restaurants),
        "attraction_count": len(attractions),
    })


# ─── POST /select ─────────────────────────────────────────────────────────────

@router.post("/select")
async def post_select(payload: SelectRequest) -> JSONResponse:
    session = await _get_session(payload.session_id)
    try:
        SessionFSM.assert_state(session, FlowState.RECOMMENDING)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Check venue is in last candidate set
    venue_id_str = str(payload.venue_id)
    candidate_ids = [str(cid) for cid in session.last_candidate_ids]
    if venue_id_str not in candidate_ids:
        raise HTTPException(status_code=400, detail="select_error:venue_not_in_candidates")

    # Find the candidate from the reachable cache (rebuild minimal card from last known data)
    # We need to fetch the venue details from the Data Service
    card: TripCandidateCard | None = None
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
    primary_mode = "transit"
    if session.transport_config and session.transport_config.modes:
        primary_mode = session.transport_config.modes[0]
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

    try:
        cards, fallback_reason = await picker.demand_mode(
            session, payload.demand_text, payload.lat, payload.lng
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
        "fallback_reason": fallback_reason,
    })


# ─── GET /should_go_home ──────────────────────────────────────────────────────

@router.get("/should_go_home")
async def get_should_go_home(
    session_id: str = Query(...),
    lat: float = Query(...),
    lng: float = Query(...),
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

    # Estimate transit time to return destination using haversine
    dest_lat, dest_lng = lat, lng  # fallback: use current location
    if session.accommodation and session.accommodation.hotel_lat and session.accommodation.hotel_lng:
        dest_lat = session.accommodation.hotel_lat
        dest_lng = session.accommodation.hotel_lng

    dist_km = haversine_distance(lat, lng, dest_lat, dest_lng)
    transit_min = max(1, int(dist_km / 12.0 * 60))  # transit ~12 km/h

    should = go_home_advisor.should_remind(session, transit_min)

    if should:
        go_home_advisor.record_reminded(session)
        await _save_session(session)

        # Calculate time remaining
        hh, mm = map(int, session.return_time.split(":"))
        today = datetime.now(UTC).date()
        from datetime import timezone
        return_dt = datetime(today.year, today.month, today.day, hh, mm, tzinfo=UTC)
        time_remaining = max(0, int((return_dt - datetime.now(UTC)).total_seconds() / 60))

        return JSONResponse({
            "session_id": session_id,
            "remind": True,
            "message": f"該回家啦！距離預定返回時間還有 {time_remaining} 分鐘，現在出發剛好！",
            "time_remaining_min": time_remaining,
        })

    return JSONResponse({
        "session_id": session_id,
        "remind": False,
        "message": None,
        "time_remaining_min": None,
    })


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
