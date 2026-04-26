from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.llm.client import llm_client
from app.services.reachability import (
    haversine_distance,
    haversine_pre_filter,
    route_time_estimate,
)
from app.services.weather import WeatherContext, get_weather_context
from app.session.models import ReachableCache, Session, TransportConfig, TripCandidateCard
from app.tools.place_adapter import place_tool_adapter

logger = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 5
_ROUTE_SEMAPHORE_LIMIT = 5
_SEARCH_LIMIT = 50
_TRIP_TARGET_PER_CATEGORY = 3
_TRIP_TARGET_TOTAL = 6
_DEMAND_TARGET_TOTAL = 3
_RELAXED_TIME_OFFSETS = (0, 10, 20)

# Bayesian prior: pull ratings toward neutral when review count is low
_BAYES_PRIOR_RATING = 3.8
_BAYES_PRIOR_COUNT = 50
# Popularity bonus: log-scaled, capped so it doesn't overwhelm rating signal
_POPULARITY_LOG_BASE = 14.0


@dataclass(frozen=True)
class _PreparedVenue:
    venue: Any
    travel_min: int
    quality_score: float
    affinity_key: str


@dataclass(frozen=True)
class _RankedVenue:
    venue: Any
    travel_min: int
    rank_score: float


@dataclass(frozen=True)
class _TripStage:
    max_minutes: int
    use_affinity: bool
    open_now: bool


@dataclass(frozen=True)
class _DemandQueryPlan:
    internal_category: str | None = None
    primary_type: str | None = None
    keyword: str | None = None
    use_default_categories: bool = False


@dataclass(frozen=True)
class _DemandStage:
    query_plan: _DemandQueryPlan
    max_minutes: int
    open_now: bool


def _venue_quality_score(
    rating: float | None,
    user_rating_count: int | None,
    mention_count: int | None,
    trend_score: float | None,
) -> float:
    """Blended quality score for ranking candidates."""
    r = float(rating) if rating is not None else _BAYES_PRIOR_RATING
    count = user_rating_count or 0

    bayesian = (count * r + _BAYES_PRIOR_COUNT * _BAYES_PRIOR_RATING) / (count + _BAYES_PRIOR_COUNT)
    popularity_bonus = min(math.log10(count + 1) / _POPULARITY_LOG_BASE, 0.3)

    social_bonus = 0.0
    if trend_score is not None:
        social_bonus += float(trend_score) * 0.1
    if mention_count:
        social_bonus += min(math.log10(mention_count + 1) / 30.0, 0.1)

    return bayesian + popularity_bonus + social_bonus


def _homing_score(
    venue_lat: float,
    venue_lng: float,
    dest_lat: float,
    dest_lng: float,
    origin_lat: float,
    origin_lng: float,
) -> float:
    dist_origin_to_dest = haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
    if dist_origin_to_dest <= 1e-6:
        return 0.0
    dist_venue_to_dest = haversine_distance(venue_lat, venue_lng, dest_lat, dest_lng)
    return max(0.0, (dist_origin_to_dest - dist_venue_to_dest) / dist_origin_to_dest)


async def pick_candidates(
    session: Session,
    origin_lat: float,
    origin_lng: float,
    *,
    transport_config: TransportConfig,
    urgency: float = 0.0,
    dest_lat: float | None = None,
    dest_lng: float | None = None,
) -> tuple[list[TripCandidateCard], list[TripCandidateCard], bool, str | None]:
    """Return up to 6 cards plus any rain-filtered cards.

    Returns (cards, rain_cards, partial, fallback_reason).
    rain_cards are outdoor venues excluded due to rain forecast; they carry a rain_note.
    """
    base_max_minutes = transport_config.max_minutes_per_leg
    widest_max_minutes = _widest_max_minutes(base_max_minutes)
    visited_ids = {str(vs.venue_id) for vs in session.visited_stops}

    # Fetch weather concurrently with initial pool load sentinel
    weather_ctx: WeatherContext = await get_weather_context()

    pool_cache: dict[bool, tuple[list[Any], list[Any]]] = {}
    prepared_cache: dict[bool, tuple[list[_PreparedVenue], list[_PreparedVenue]]] = {}

    async def get_prepared_pools(open_now: bool) -> tuple[list[_PreparedVenue], list[_PreparedVenue]]:
        cached = prepared_cache.get(open_now)
        if cached is not None:
            return cached

        rest_venues_raw, attr_venues_raw = await _load_trip_pools(
            open_now=open_now,
            visited_ids=visited_ids,
            pool_cache=pool_cache,
        )

        if weather_ctx.is_raining_likely:
            rest_venues, _ = _filter_outdoor_on_rain(rest_venues_raw)
            attr_venues, _ = _filter_outdoor_on_rain(attr_venues_raw)
        else:
            rest_venues, attr_venues = rest_venues_raw, attr_venues_raw

        prepared = await asyncio.gather(
            _prepare_venues(
                rest_venues,
                origin_lat,
                origin_lng,
                max_minutes=widest_max_minutes,
                primary_mode=transport_config.mode,
            ),
            _prepare_venues(
                attr_venues,
                origin_lat,
                origin_lng,
                max_minutes=widest_max_minutes,
                primary_mode=transport_config.mode,
            ),
        )
        prepared_cache[open_now] = (prepared[0], prepared[1])
        return prepared[0], prepared[1]

    chosen_stage: _TripStage | None = None
    final_rest_ranked: list[_RankedVenue] = []
    final_attr_ranked: list[_RankedVenue] = []

    u = min(1.0, max(0.0, float(urgency)))
    dlat, dlng = dest_lat, dest_lng

    for stage in _trip_stages(base_max_minutes):
        rest_prepared, attr_prepared = await get_prepared_pools(stage.open_now)
        final_rest_ranked = _rank_trip_venues(
            rest_prepared,
            session,
            max_minutes=stage.max_minutes,
            use_affinity=stage.use_affinity,
            urgency=u,
            dest_lat=dlat,
            dest_lng=dlng,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
        )
        final_attr_ranked = _rank_trip_venues(
            attr_prepared,
            session,
            max_minutes=stage.max_minutes,
            use_affinity=stage.use_affinity,
            urgency=u,
            dest_lat=dlat,
            dest_lng=dlng,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
        )
        chosen_stage = stage
        if (
            len(final_rest_ranked) >= _TRIP_TARGET_PER_CATEGORY
            and len(final_attr_ranked) >= _TRIP_TARGET_PER_CATEGORY
        ):
            break

    if chosen_stage is None:
        raise ValueError("candidates_error:data_service_unavailable:no_venues")

    selected = _select_trip_candidates(final_rest_ranked, final_attr_ranked)
    partial = len(selected) < _TRIP_TARGET_TOTAL
    fallback_reason = _build_trip_fallback_reason(
        base_max_minutes,
        chosen_stage,
        partial=partial,
    )
    cards = await _build_cards_from_ranked(
        selected,
        gene=session.travel_gene or "旅人",
        partial=partial,
    )

    # Build rain-filtered disclosure cards (attraction only; restaurants are rarely purely outdoor)
    rain_cards: list[TripCandidateCard] = []
    if weather_ctx.is_raining_likely:
        _, rest_excluded = _filter_outdoor_on_rain(
            await _get_pool_raw(pool_cache, open_now=True, category="food", visited_ids=visited_ids)
        )
        _, attr_excluded = _filter_outdoor_on_rain(
            await _get_pool_raw(pool_cache, open_now=True, category="attraction", visited_ids=visited_ids)
        )
        all_excluded = _dedupe_venues(rest_excluded + attr_excluded)
        if all_excluded:
            rain_note = _build_rain_note(weather_ctx)
            rain_ranked = await _prepare_venues(
                all_excluded,
                origin_lat,
                origin_lng,
                max_minutes=widest_max_minutes,
                primary_mode=transport_config.mode,
            )
            rain_ranked_sorted = sorted(
                rain_ranked,
                key=lambda p: (-p.quality_score, p.travel_min, getattr(p.venue, "name", "")),
            )
            rain_cards = await _build_rain_cards(rain_ranked_sorted[:_TRIP_TARGET_TOTAL], rain_note=rain_note)

    session.reachable_cache = ReachableCache(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        venue_ids=[c.venue_id for c in cards],
        expires_at=datetime.now(UTC) + timedelta(minutes=_CACHE_TTL_MINUTES),
    )
    session.last_candidate_ids = [c.venue_id for c in cards]

    return cards, rain_cards, partial, fallback_reason


async def demand_mode(
    session: Session,
    demand_text: str,
    origin_lat: float,
    origin_lng: float,
    *,
    transport_config: TransportConfig,
) -> tuple[list[TripCandidateCard], list[TripCandidateCard], str | None]:
    """Return up to 3 alternative venues matching the demand text plus any rain-filtered cards.

    Returns (cards, rain_cards, fallback_reason).
    """
    base_max_minutes = transport_config.max_minutes_per_leg * 2
    widest_max_minutes = _widest_max_minutes(base_max_minutes)

    (llm_category, llm_primary_type), weather_ctx = await asyncio.gather(
        _llm_parse_demand(demand_text),
        get_weather_context(),
    )

    logger.info(
        "demand_mode LLM parse: text=%r → category=%r, primary_type=%r",
        demand_text,
        llm_category,
        llm_primary_type,
    )

    visited_ids = {str(vs.venue_id) for vs in session.visited_stops}
    strict_query, relaxed_query = _build_demand_query_plans(
        demand_text=demand_text,
        llm_category=llm_category,
        llm_primary_type=llm_primary_type,
    )

    prepared_cache: dict[tuple[_DemandQueryPlan, bool], list[_PreparedVenue]] = {}
    raw_venue_cache: dict[tuple[_DemandQueryPlan, bool], list[Any]] = {}

    async def get_prepared(plan: _DemandQueryPlan, open_now: bool) -> list[_PreparedVenue]:
        cache_key = (plan, open_now)
        cached = prepared_cache.get(cache_key)
        if cached is not None:
            return cached

        venues_raw = await _load_demand_venues(plan, open_now=open_now, visited_ids=visited_ids)
        raw_venue_cache[cache_key] = venues_raw

        venues = venues_raw
        if weather_ctx.is_raining_likely:
            venues, _ = _filter_outdoor_on_rain(venues_raw)

        prepared = await _prepare_venues(
            venues,
            origin_lat,
            origin_lng,
            max_minutes=widest_max_minutes,
            primary_mode=transport_config.mode,
        )
        prepared_cache[cache_key] = prepared
        return prepared

    chosen_stage: _DemandStage | None = None
    final_ranked: list[_RankedVenue] = []

    for stage in _demand_stages(base_max_minutes, strict_query, relaxed_query):
        prepared = await get_prepared(stage.query_plan, stage.open_now)
        final_ranked = _rank_demand_venues(prepared, max_minutes=stage.max_minutes)
        chosen_stage = stage
        if len(final_ranked) >= _DEMAND_TARGET_TOTAL:
            break

    if chosen_stage is None:
        raise ValueError("candidates_error:data_service_unavailable:no_venues")

    selected = final_ranked[:_DEMAND_TARGET_TOTAL]
    fallback_reason = _build_demand_fallback_reason(
        base_max_minutes,
        chosen_stage,
        strict_query=strict_query,
        partial=len(selected) < _DEMAND_TARGET_TOTAL,
    )
    cards = await _build_cards_from_ranked(
        selected,
        gene=session.travel_gene or "旅人",
        partial=False,
    )

    # Build rain-filtered disclosure cards from the chosen stage's raw pool
    rain_cards: list[TripCandidateCard] = []
    if weather_ctx.is_raining_likely:
        chosen_key = (chosen_stage.query_plan, chosen_stage.open_now)
        raw_venues = raw_venue_cache.get(chosen_key, [])
        _, excluded = _filter_outdoor_on_rain(raw_venues)
        if excluded:
            rain_note = _build_rain_note(weather_ctx)
            excluded_prepared = await _prepare_venues(
                excluded,
                origin_lat,
                origin_lng,
                max_minutes=widest_max_minutes,
                primary_mode=transport_config.mode,
            )
            excluded_sorted = sorted(
                excluded_prepared,
                key=lambda p: (p.travel_min, -p.quality_score, getattr(p.venue, "name", "")),
            )
            rain_cards = await _build_rain_cards(excluded_sorted[:_DEMAND_TARGET_TOTAL], rain_note=rain_note)

    session.reachable_cache = ReachableCache(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        venue_ids=[c.venue_id for c in cards],
        expires_at=datetime.now(UTC) + timedelta(minutes=_CACHE_TTL_MINUTES),
    )
    session.last_candidate_ids = [c.venue_id for c in cards]

    return cards, rain_cards, fallback_reason


async def _load_trip_pools(
    *,
    open_now: bool,
    visited_ids: set[str],
    pool_cache: dict[bool, tuple[list[Any], list[Any]]],
) -> tuple[list[Any], list[Any]]:
    cached = pool_cache.get(open_now)
    if cached is not None:
        return cached

    rest_venues, attr_venues = await asyncio.gather(
        _search_places_or_raise(
            internal_category="food",
            open_now=True if open_now else None,
            limit=_SEARCH_LIMIT,
        ),
        _search_places_or_raise(
            internal_category="attraction",
            open_now=True if open_now else None,
            limit=_SEARCH_LIMIT,
        ),
    )
    filtered = (
        _dedupe_venues(_filter_visited(rest_venues, visited_ids)),
        _dedupe_venues(_filter_visited(attr_venues, visited_ids)),
    )
    pool_cache[open_now] = filtered
    return filtered


async def _load_demand_venues(
    query_plan: _DemandQueryPlan,
    *,
    open_now: bool,
    visited_ids: set[str],
) -> list[Any]:
    if query_plan.use_default_categories:
        venues = []
        for internal_category in ("food", "attraction"):
            venues.extend(
                await _search_places_or_raise(
                    internal_category=internal_category,
                    open_now=True if open_now else None,
                    limit=_SEARCH_LIMIT,
                )
            )
    else:
        venues = await _search_places_or_raise(
            internal_category=query_plan.internal_category,
            primary_type=query_plan.primary_type,
            keyword=query_plan.keyword,
            open_now=True if open_now else None,
            limit=_SEARCH_LIMIT,
        )

    return _dedupe_venues(_filter_visited(venues, visited_ids))


async def _search_places_or_raise(**kwargs: Any) -> list[Any]:
    result = await place_tool_adapter.search_places(**kwargs)
    if result.status == "error":
        raise ValueError(
            f"candidates_error:data_service_unavailable:{result.error or 'search_error'}"
        )
    return list(result.items)


def _filter_outdoor_on_rain(venues: list[Any]) -> tuple[list[Any], list[Any]]:
    """Split venues into (kept, excluded) when rain is forecast.

    A venue is excluded only if outdoor=True AND indoor is not True.
    Unknown outdoor status (None) → kept, to avoid over-filtering.
    """
    kept: list[Any] = []
    excluded: list[Any] = []
    for venue in venues:
        outdoor = getattr(venue, "outdoor", None)
        indoor = getattr(venue, "indoor", None)
        if outdoor is True and indoor is not True:
            excluded.append(venue)
        else:
            kept.append(venue)
    return kept, excluded


def _build_rain_note(weather_ctx: WeatherContext) -> str:
    if weather_ctx.rain_probability is not None:
        return f"預報降雨（機率約 {weather_ctx.rain_probability}%），此景點為戶外場地，雨天體驗較差"
    return "預報有雨，此景點為戶外場地，雨天體驗較差"


async def _get_pool_raw(
    pool_cache: dict[bool, tuple[list[Any], list[Any]]],
    *,
    open_now: bool,
    category: str,
    visited_ids: set[str],
) -> list[Any]:
    """Return the raw venue pool from cache, fetching if not yet populated."""
    cached = pool_cache.get(open_now)
    if cached is not None:
        rest_raw, attr_raw = cached
        return rest_raw if category == "food" else attr_raw
    # Not yet cached — fetch directly (this path only hit when pool_cache was never populated)
    venues = await _search_places_or_raise(
        internal_category=category,
        open_now=True if open_now else None,
        limit=_SEARCH_LIMIT,
    )
    return _dedupe_venues(_filter_visited(venues, visited_ids))


async def _build_rain_cards(
    prepared: list[_PreparedVenue],
    *,
    rain_note: str,
) -> list[TripCandidateCard]:
    """Build TripCandidateCard list for rain-filtered venues with rain_note set."""
    if not prepared:
        return []
    cards: list[TripCandidateCard] = []
    for idx, item in enumerate(prepared):
        venue = item.venue
        cards.append(
            TripCandidateCard(
                venue_id=getattr(venue, "venue_id", str(idx)),
                name=venue.name,
                name_en=venue.raw_payload.get("name_en") or None,
                category="restaurant" if _is_restaurant(venue) else "attraction",
                primary_type=getattr(venue, "primary_type", None),
                address=getattr(venue, "formatted_address", None),
                lat=venue.lat or 0.0,
                lng=venue.lng or 0.0,
                rating=getattr(venue, "rating", None),
                distance_min=item.travel_min,
                why_recommended="",
                rain_note=rain_note,
                vibe_tags=getattr(venue, "vibe_tags", None) or [],
                mention_count=getattr(venue, "mention_count", None),
                sentiment_score=getattr(venue, "sentiment_score", None),
                trend_score=getattr(venue, "trend_score", None),
            )
        )
    return cards


def _filter_visited(venues: list[Any], visited_ids: set[str]) -> list[Any]:
    if not visited_ids:
        return list(venues)
    return [
        venue
        for venue in venues
        if str(getattr(venue, "venue_id", "")) not in visited_ids
    ]


def _dedupe_venues(venues: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[str] = set()
    for venue in venues:
        venue_id = str(getattr(venue, "venue_id", ""))
        if venue_id in seen:
            continue
        seen.add(venue_id)
        deduped.append(venue)
    return deduped


async def _prepare_venues(
    venues: list[Any],
    origin_lat: float,
    origin_lng: float,
    *,
    max_minutes: int,
    primary_mode: str,
) -> list[_PreparedVenue]:
    if not venues:
        return []

    semaphore = asyncio.Semaphore(_ROUTE_SEMAPHORE_LIMIT)
    prefiltered = haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes, primary_mode)
    tasks = [
        route_time_estimate(venue, origin_lat, origin_lng, primary_mode, semaphore)
        for venue in prefiltered
    ]
    times = await asyncio.gather(*tasks)

    prepared: list[_PreparedVenue] = []
    for venue, travel_min in zip(prefiltered, times):
        prepared.append(
            _PreparedVenue(
                venue=venue,
                travel_min=travel_min,
                quality_score=_venue_quality_score(
                    rating=getattr(venue, "rating", None),
                    user_rating_count=getattr(venue, "user_rating_count", None),
                    mention_count=getattr(venue, "mention_count", None),
                    trend_score=getattr(venue, "trend_score", None),
                ),
                affinity_key=(
                    getattr(venue, "primary_type", None)
                    or getattr(venue, "category", None)
                    or ""
                ),
            )
        )
    return prepared


def _rank_trip_venues(
    prepared: list[_PreparedVenue],
    session: Session,
    *,
    max_minutes: int,
    use_affinity: bool,
    urgency: float = 0.0,
    dest_lat: float | None = None,
    dest_lng: float | None = None,
    origin_lat: float = 0.0,
    origin_lng: float = 0.0,
) -> list[_RankedVenue]:
    ranked: list[_RankedVenue] = []
    use_homing = (
        urgency > 0.0
        and dest_lat is not None
        and dest_lng is not None
    )
    for item in prepared:
        if item.travel_min > max_minutes:
            continue
        affinity = 1.0
        if use_affinity:
            affinity = session.gene_affinity_weights.get(item.affinity_key, 1.0)
        base = affinity * item.quality_score
        homing = 0.0
        if use_homing:
            vlat = getattr(item.venue, "lat", None)
            vlng = getattr(item.venue, "lng", None)
            if vlat is not None and vlng is not None:
                homing = _homing_score(
                    float(vlat),
                    float(vlng),
                    float(dest_lat),
                    float(dest_lng),
                    origin_lat,
                    origin_lng,
                )
        rank_score = base * (1.0 - urgency) + homing * urgency
        ranked.append(
            _RankedVenue(
                venue=item.venue,
                travel_min=item.travel_min,
                rank_score=rank_score,
            )
        )

    ranked.sort(key=lambda item: (-item.rank_score, item.travel_min, getattr(item.venue, "name", "")))
    return ranked


def _rank_demand_venues(
    prepared: list[_PreparedVenue],
    *,
    max_minutes: int,
) -> list[_RankedVenue]:
    ranked = [
        _RankedVenue(
            venue=item.venue,
            travel_min=item.travel_min,
            rank_score=item.quality_score,
        )
        for item in prepared
        if item.travel_min <= max_minutes
    ]
    ranked.sort(key=lambda item: (item.travel_min, -item.rank_score, getattr(item.venue, "name", "")))
    return ranked


def _select_trip_candidates(
    rest_ranked: list[_RankedVenue],
    attr_ranked: list[_RankedVenue],
) -> list[_RankedVenue]:
    selected = list(rest_ranked[:_TRIP_TARGET_PER_CATEGORY]) + list(attr_ranked[:_TRIP_TARGET_PER_CATEGORY])
    selected_ids = {str(getattr(item.venue, "venue_id", "")) for item in selected}

    remaining = [
        item
        for item in list(rest_ranked[_TRIP_TARGET_PER_CATEGORY:]) + list(attr_ranked[_TRIP_TARGET_PER_CATEGORY:])
        if str(getattr(item.venue, "venue_id", "")) not in selected_ids
    ]
    remaining.sort(key=lambda item: (-item.rank_score, item.travel_min, getattr(item.venue, "name", "")))

    selected.extend(remaining[: max(0, _TRIP_TARGET_TOTAL - len(selected))])
    return selected[:_TRIP_TARGET_TOTAL]


async def _build_cards_from_ranked(
    ranked: list[_RankedVenue],
    *,
    gene: str,
    partial: bool,
) -> list[TripCandidateCard]:
    why_reasons = await _batch_why_recommended(
        [(item.venue, item.travel_min) for item in ranked],
        gene,
    )

    cards: list[TripCandidateCard] = []
    for idx, item in enumerate(ranked):
        venue = item.venue
        cards.append(
            TripCandidateCard(
                venue_id=getattr(venue, "venue_id", str(idx)),
                name=venue.name,
                name_en=venue.raw_payload.get("name_en") or None,
                category="restaurant" if _is_restaurant(venue) else "attraction",
                primary_type=getattr(venue, "primary_type", None),
                address=getattr(venue, "formatted_address", None),
                lat=venue.lat or 0.0,
                lng=venue.lng or 0.0,
                rating=getattr(venue, "rating", None),
                distance_min=item.travel_min,
                why_recommended=why_reasons[idx] if idx < len(why_reasons) else "",
                partial=partial,
                vibe_tags=getattr(venue, "vibe_tags", None) or [],
                mention_count=getattr(venue, "mention_count", None),
                sentiment_score=getattr(venue, "sentiment_score", None),
                trend_score=getattr(venue, "trend_score", None),
            )
        )
    return cards


def _widest_max_minutes(base_max_minutes: int) -> int:
    return base_max_minutes + _RELAXED_TIME_OFFSETS[-1]


def _trip_stages(base_max_minutes: int) -> list[_TripStage]:
    widest = _widest_max_minutes(base_max_minutes)
    stages = [
        _TripStage(max_minutes=base_max_minutes + offset, use_affinity=True, open_now=True)
        for offset in _RELAXED_TIME_OFFSETS
    ]
    stages.append(_TripStage(max_minutes=widest, use_affinity=False, open_now=True))
    stages.append(_TripStage(max_minutes=widest, use_affinity=False, open_now=False))
    return stages


def _demand_stages(
    base_max_minutes: int,
    strict_query: _DemandQueryPlan,
    relaxed_query: _DemandQueryPlan,
) -> list[_DemandStage]:
    widest = _widest_max_minutes(base_max_minutes)
    stages = [
        _DemandStage(
            query_plan=strict_query,
            max_minutes=base_max_minutes + offset,
            open_now=True,
        )
        for offset in _RELAXED_TIME_OFFSETS
    ]
    if relaxed_query != strict_query:
        stages.append(
            _DemandStage(
                query_plan=relaxed_query,
                max_minutes=widest,
                open_now=True,
            )
        )
    stages.append(
        _DemandStage(
            query_plan=relaxed_query,
            max_minutes=widest,
            open_now=False,
        )
    )
    return stages


def _build_demand_query_plans(
    *,
    demand_text: str,
    llm_category: str | None,
    llm_primary_type: str | None,
) -> tuple[_DemandQueryPlan, _DemandQueryPlan]:
    stripped_text = demand_text.strip()
    if llm_category:
        strict_query = _DemandQueryPlan(
            internal_category=llm_category,
            primary_type=llm_primary_type,
        )
        relaxed_query = _DemandQueryPlan(internal_category=llm_category)
        return strict_query, relaxed_query

    strict_query = _DemandQueryPlan(keyword=stripped_text or None)
    relaxed_query = _DemandQueryPlan(use_default_categories=True)
    return strict_query, relaxed_query


def _build_trip_fallback_reason(
    base_max_minutes: int,
    stage: _TripStage,
    *,
    partial: bool,
) -> str | None:
    steps: list[str] = []
    if stage.max_minutes > base_max_minutes:
        steps.append(f"expanded_max_minutes_to_{stage.max_minutes}")
    if not stage.use_affinity:
        steps.append("relaxed_gene_affinity")
    if not stage.open_now:
        steps.append("dropped_open_now")
    if partial:
        steps.append("partial_results")
    return "; ".join(steps) or None


def _build_demand_fallback_reason(
    base_max_minutes: int,
    stage: _DemandStage,
    *,
    strict_query: _DemandQueryPlan,
    partial: bool,
) -> str | None:
    steps: list[str] = []
    if stage.max_minutes > base_max_minutes:
        steps.append(f"expanded_max_minutes_to_{stage.max_minutes}")
    if stage.query_plan != strict_query:
        steps.append("relaxed_demand_filters")
    if not stage.open_now:
        steps.append("dropped_open_now")
    if partial:
        steps.append("partial_results")
    return "; ".join(steps) or None


_VALID_CATEGORIES = ("food", "attraction", "shopping", "nightlife", "lodging", "other")

_FOOD_PRIMARY_TYPES = (
    "american_restaurant,asian_restaurant,bakery,bar,barbecue_restaurant,bistro,"
    "breakfast_restaurant,brunch_restaurant,buffet_restaurant,cafe,cake_shop,"
    "cantonese_restaurant,chicken_restaurant,chinese_noodle_restaurant,chinese_restaurant,"
    "cocktail_bar,coffee_shop,dessert_restaurant,dessert_shop,dim_sum_restaurant,"
    "dumpling_restaurant,european_restaurant,fast_food_restaurant,fine_dining_restaurant,"
    "french_restaurant,fusion_restaurant,german_restaurant,hamburger_restaurant,"
    "hot_pot_restaurant,ice_cream_shop,indian_restaurant,italian_restaurant,"
    "japanese_curry_restaurant,japanese_izakaya_restaurant,japanese_restaurant,"
    "kebab_shop,korean_barbecue_restaurant,korean_restaurant,mediterranean_restaurant,"
    "mexican_restaurant,noodle_shop,pizza_restaurant,pub,ramen_restaurant,restaurant,"
    "seafood_restaurant,snack_bar,sushi_restaurant,taiwanese_restaurant,tea_house,"
    "thai_restaurant,tonkatsu_restaurant,vegan_restaurant,vegetarian_restaurant,"
    "vietnamese_restaurant,western_restaurant,wine_bar,yakiniku_restaurant,yakitori_restaurant"
)
_ATTRACTION_PRIMARY_TYPES = (
    "amphitheatre,amusement_center,art_gallery,art_museum,art_studio,botanical_garden,"
    "bridge,buddhist_temple,city_park,community_center,concert_hall,cultural_center,"
    "cultural_landmark,dog_park,event_venue,farmers_market,garden,hiking_area,"
    "historical_landmark,history_museum,library,live_music_venue,movie_theater,museum,"
    "nature_preserve,night_club,observation_deck,park,performing_arts_theater,"
    "place_of_worship,playground,plaza,public_bath,scenic_spot,sculpture,shinto_shrine,"
    "tourist_attraction,zoo"
)

_LLM_PARSE_PROMPT = """\
你是台北旅遊助手，負責把用戶需求轉成結構化搜尋參數。

用戶說：「{demand_text}」

請根據需求選出最合適的 internal_category 和 primary_type。

internal_category 只能選以下其中一個：
food, attraction, shopping, nightlife, lodging, other

food 的 primary_type 可以選以下其中一個（或 null）：
{food_types}

attraction 的 primary_type 可以選以下其中一個（或 null）：
{attraction_types}

其他 category 的 primary_type 填 null。

回傳嚴格 JSON，不加任何說明文字：
{{"internal_category": "...", "primary_type": "..." 或 null}}
"""


async def _llm_parse_demand(demand_text: str) -> tuple[str | None, str | None]:
    """Return (internal_category, primary_type) inferred by LLM from demand text."""
    prompt = _LLM_PARSE_PROMPT.format(
        demand_text=demand_text,
        food_types=_FOOD_PRIMARY_TYPES,
        attraction_types=_ATTRACTION_PRIMARY_TYPES,
    )
    try:
        result = await llm_client.generate_json(prompt)
        if not isinstance(result, dict):
            return None, None
        cat = result.get("internal_category")
        pt = result.get("primary_type")
        if cat not in _VALID_CATEGORIES or cat == "other":
            cat = None
        if not isinstance(pt, str) or not pt:
            pt = None
        return cat, pt
    except Exception as exc:
        logger.warning("_llm_parse_demand failed: %s", exc)
        return None, None


def _is_restaurant(venue: Any) -> bool:
    cat = (
        getattr(venue, "category", None)
        or getattr(venue, "source_category", None)
        or ""
    ).lower()
    return cat in {"food", "restaurant", "cafe", "bar", "nightmarket"}


async def _batch_why_recommended(
    scored: list[tuple[Any, int]],
    gene: str,
) -> list[str]:
    """Single LLM call returning one sentence per venue."""
    if not scored:
        return []

    venue_list = "\n".join(
        f"{i + 1}. {v.name} ({getattr(v, 'primary_type', '') or getattr(v, 'category', '')})"
        for i, (v, _) in enumerate(scored)
    )
    prompt = (
        f"你是台北旅遊達人。使用者的旅遊基因是「{gene}」。"
        f"請為以下每個地點各寫一句中文推薦理由（15字以內），回傳 JSON 陣列，例如 [\"推薦理由1\", \"推薦理由2\"]。\n\n"
        f"{venue_list}"
    )

    try:
        text = await llm_client.generate_text(prompt)
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            arr = json.loads(text[start:end + 1])
            if isinstance(arr, list):
                return [str(x) for x in arr]
    except Exception as exc:
        logger.warning("batch why_recommended LLM failed: %s", exc)

    return ["值得一訪！" for _ in scored]
