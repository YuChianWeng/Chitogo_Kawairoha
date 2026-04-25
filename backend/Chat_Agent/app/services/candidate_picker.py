from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.llm.client import llm_client
from app.services.reachability import (
    graduated_fallback,
    haversine_pre_filter,
    route_time_estimate,
)
from app.session.models import ReachableCache, Session, TripCandidateCard
from app.tools.place_adapter import place_tool_adapter

logger = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 5
_ROUTE_SEMAPHORE_LIMIT = 5


def _is_cache_valid(cache: ReachableCache | None, lat: float, lng: float) -> bool:
    if cache is None:
        return False
    now = datetime.now(UTC)
    if cache.expires_at < now:
        return False
    # Invalidate if origin moved more than ~100m (roughly 0.001 degrees)
    if abs(cache.origin_lat - lat) > 0.001 or abs(cache.origin_lng - lng) > 0.001:
        return False
    return True


async def pick_candidates(
    session: Session,
    origin_lat: float,
    origin_lng: float,
) -> tuple[list[TripCandidateCard], bool, str | None]:
    """Return (cards, partial, fallback_reason) — exactly 6 cards (3 rest + 3 attr) if possible."""
    transport_config = session.transport_config
    max_minutes = transport_config.max_minutes_per_leg if transport_config else 30
    modes = transport_config.modes if transport_config else ["transit"]
    primary_mode = modes[0] if modes else "transit"

    # Fetch venues from Data Service
    try:
        rest_result = await place_tool_adapter.search_places(
            internal_category="food",
            limit=50,
        )
        attr_result = await place_tool_adapter.search_places(
            internal_category="attraction",
            limit=50,
        )
        all_venues = list(rest_result.items) + list(attr_result.items)
    except Exception as exc:
        raise ValueError(f"candidates_error:data_service_unavailable:{exc}") from exc

    if not all_venues:
        raise ValueError("candidates_error:data_service_unavailable:no_venues")

    # Filter by reachability
    restaurants_raw = [v for v in all_venues if _is_restaurant(v)]
    attractions_raw = [v for v in all_venues if not _is_restaurant(v)]

    semaphore = asyncio.Semaphore(_ROUTE_SEMAPHORE_LIMIT)

    async def score_venues(venues: list[Any]) -> list[tuple[Any, int]]:
        pre = haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes, primary_mode)
        tasks = [
            route_time_estimate(v, origin_lat, origin_lng, primary_mode, semaphore)
            for v in pre
        ]
        times = await asyncio.gather(*tasks)
        within = [(v, t) for v, t in zip(pre, times) if t <= max_minutes]
        # Sort by affinity score * rating
        def rank(item: tuple[Any, int]) -> float:
            v, _ = item
            category = getattr(v, "primary_type", None) or getattr(v, "category", None) or ""
            affinity = session.gene_affinity_weights.get(category, 1.0)
            base_rating = getattr(v, "rating", None) or 3.0
            return affinity * base_rating

        within.sort(key=rank, reverse=True)
        return within

    rest_scored, attr_scored = await asyncio.gather(
        score_venues(restaurants_raw),
        score_venues(attractions_raw),
    )

    # Try 3+3 split, fall back to partial
    partial = False
    fallback_reason: str | None = None

    top_rest = rest_scored[:3]
    top_attr = attr_scored[:3]

    if len(top_rest) < 3 or len(top_attr) < 3:
        partial = True
        # Pad with whatever we have
        all_scored = rest_scored + attr_scored
        all_scored.sort(key=lambda x: x[1])  # sort by travel time
        combined = all_scored[:6]
        top_rest = [(v, t) for v, t in combined if _is_restaurant(v)][:3]
        top_attr = [(v, t) for v, t in combined if not _is_restaurant(v)][:3]
        fallback_reason = f"partial: only {len(rest_scored)} restaurants and {len(attr_scored)} attractions reachable"

    # Build candidate list
    selected = top_rest + top_attr

    # Batch LLM call for why_recommended
    gene = session.travel_gene or "旅人"
    why_reasons = await _batch_why_recommended(selected, gene)

    cards: list[TripCandidateCard] = []
    for idx, (v, travel_min) in enumerate(selected):
        card = TripCandidateCard(
            venue_id=getattr(v, "venue_id", str(idx)),
            name=v.name,
            category="restaurant" if _is_restaurant(v) else "attraction",
            primary_type=getattr(v, "primary_type", None),
            address=getattr(v, "formatted_address", None),
            lat=v.lat or 0.0,
            lng=v.lng or 0.0,
            rating=getattr(v, "rating", None),
            distance_min=travel_min,
            why_recommended=why_reasons[idx] if idx < len(why_reasons) else "",
            partial=partial,
        )
        cards.append(card)

    # Update reachable cache
    session.reachable_cache = ReachableCache(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        venue_ids=[c.venue_id for c in cards],
        expires_at=datetime.now(UTC) + timedelta(minutes=_CACHE_TTL_MINUTES),
    )
    session.last_candidate_ids = [c.venue_id for c in cards]

    return cards, partial, fallback_reason


async def demand_mode(
    session: Session,
    demand_text: str,
    origin_lat: float,
    origin_lng: float,
) -> tuple[list[TripCandidateCard], str | None]:
    """Return up to 3 alternative venues matching the demand text."""
    transport_config = session.transport_config
    max_minutes = transport_config.max_minutes_per_leg if transport_config else 30
    modes = transport_config.modes if transport_config else ["transit"]
    primary_mode = modes[0] if modes else "transit"

    try:
        result = await place_tool_adapter.search_places(keyword=demand_text, limit=20)
        venues = list(result.items)
    except Exception as exc:
        raise ValueError(f"candidates_error:data_service_unavailable:{exc}") from exc

    semaphore = asyncio.Semaphore(_ROUTE_SEMAPHORE_LIMIT)
    pre = haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes * 2, primary_mode)
    tasks = [route_time_estimate(v, origin_lat, origin_lng, primary_mode, semaphore) for v in pre]
    times = await asyncio.gather(*tasks)
    within = [(v, t) for v, t in zip(pre, times) if t <= max_minutes * 2]
    within.sort(key=lambda x: x[1])
    top3 = within[:3]

    fallback_reason: str | None = None
    if len(top3) < 3:
        fallback_reason = f"only {len(top3)} alternatives found within range"

    gene = session.travel_gene or "旅人"
    why_reasons = await _batch_why_recommended(top3, gene)

    cards: list[TripCandidateCard] = []
    for idx, (v, travel_min) in enumerate(top3):
        card = TripCandidateCard(
            venue_id=getattr(v, "venue_id", str(idx)),
            name=v.name,
            category="restaurant" if _is_restaurant(v) else "attraction",
            primary_type=getattr(v, "primary_type", None),
            address=getattr(v, "formatted_address", None),
            lat=v.lat or 0.0,
            lng=v.lng or 0.0,
            rating=getattr(v, "rating", None),
            distance_min=travel_min,
            why_recommended=why_reasons[idx] if idx < len(why_reasons) else "",
        )
        cards.append(card)

    return cards, fallback_reason


def _is_restaurant(venue: Any) -> bool:
    cat = (
        getattr(venue, "category", None) or
        getattr(venue, "source_category", None) or
        ""
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
        f"{i+1}. {v.name} ({getattr(v, 'primary_type', '') or getattr(v, 'category', '')})"
        for i, (v, _) in enumerate(scored)
    )
    prompt = (
        f"你是台北旅遊達人。使用者的旅遊基因是「{gene}」。"
        f"請為以下每個地點各寫一句中文推薦理由（15字以內），回傳 JSON 陣列，例如 [\"推薦理由1\", \"推薦理由2\"]。\n\n"
        f"{venue_list}"
    )

    try:
        text = await llm_client.generate_text(prompt)
        # Extract JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            arr = json.loads(text[start:end + 1])
            if isinstance(arr, list):
                return [str(x) for x in arr]
    except Exception as exc:
        logger.warning("batch why_recommended LLM failed: %s", exc)

    return ["值得一訪！" for _ in scored]
