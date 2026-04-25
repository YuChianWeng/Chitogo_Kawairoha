from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from app.llm.client import llm_client
from app.services.reachability import (
    graduated_fallback,
    haversine_pre_filter,
    route_time_estimate,
)
from app.session.models import ReachableCache, Session, TransportConfig, TripCandidateCard
from app.tools.place_adapter import place_tool_adapter

logger = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 5
_ROUTE_SEMAPHORE_LIMIT = 5

# Bayesian prior: pull ratings toward neutral when review count is low
_BAYES_PRIOR_RATING = 3.8   # neutral quality baseline
_BAYES_PRIOR_COUNT = 50     # reviews needed to trust the rating fully
# Popularity bonus: log-scaled, capped so it doesn't overwhelm rating signal
_POPULARITY_LOG_BASE = 14.0  # log10(10 000) / 14 ≈ 0.29 max bonus


def _venue_quality_score(
    rating: float | None,
    user_rating_count: int | None,
    mention_count: int | None,
    trend_score: float | None,
) -> float:
    """
    Blended quality score for ranking candidates.

    Components:
    - Bayesian rating: smooths raw rating toward the prior when reviews are scarce
    - Popularity bonus: log-scaled review count adds up to +0.3 for very popular venues
    - Social bonus: mention_count / trend_score add a small signal when present
    """
    r = float(rating) if rating is not None else _BAYES_PRIOR_RATING
    count = user_rating_count or 0

    # Bayesian average: weight rating by review volume, pull toward prior when count is low
    bayesian = (count * r + _BAYES_PRIOR_COUNT * _BAYES_PRIOR_RATING) / (count + _BAYES_PRIOR_COUNT)

    # Popularity bonus: +0 for 0 reviews → +~0.29 for 10 000 reviews
    popularity_bonus = min(math.log10(count + 1) / _POPULARITY_LOG_BASE, 0.3)

    # Social bonus: trend_score [0,1] adds up to +0.1; mention_count adds up to +0.1
    social_bonus = 0.0
    if trend_score is not None:
        social_bonus += float(trend_score) * 0.1
    if mention_count:
        social_bonus += min(math.log10(mention_count + 1) / 30.0, 0.1)

    return bayesian + popularity_bonus + social_bonus


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
    *,
    transport_config: TransportConfig,
) -> tuple[list[TripCandidateCard], bool, str | None]:
    """Return (cards, partial, fallback_reason) — exactly 6 cards (3 rest + 3 attr) if possible."""
    max_minutes = transport_config.max_minutes_per_leg
    primary_mode = transport_config.mode

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

    # Exclude already-visited venues
    visited_ids = {str(vs.venue_id) for vs in session.visited_stops}
    all_venues = [v for v in all_venues if str(getattr(v, "venue_id", "")) not in visited_ids]

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
        # Sort by affinity × blended quality (Bayesian rating + popularity + social)
        def rank(item: tuple[Any, int]) -> float:
            v, _ = item
            category = getattr(v, "primary_type", None) or getattr(v, "category", None) or ""
            affinity = session.gene_affinity_weights.get(category, 1.0)
            quality = _venue_quality_score(
                rating=getattr(v, "rating", None),
                user_rating_count=getattr(v, "user_rating_count", None),
                mention_count=getattr(v, "mention_count", None),
                trend_score=getattr(v, "trend_score", None),
            )
            return affinity * quality

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
    *,
    transport_config: TransportConfig,
) -> tuple[list[TripCandidateCard], str | None]:
    """Return up to 3 alternative venues matching the demand text."""
    max_minutes = transport_config.max_minutes_per_leg
    primary_mode = transport_config.mode

    # Use LLM to map free-form demand text to structured search parameters
    llm_category, llm_primary_type = await _llm_parse_demand(demand_text)
    logger.info(
        "demand_mode LLM parse: text=%r → category=%r, primary_type=%r",
        demand_text, llm_category, llm_primary_type,
    )

    try:
        if llm_category:
            # Structured search: use LLM-inferred category (+ optional primary_type)
            r = await place_tool_adapter.search_places(
                internal_category=llm_category,
                primary_type=llm_primary_type,
                limit=50,
            )
            venues = list(r.items)
            # If primary_type filter was too narrow, retry with category only
            if not venues and llm_primary_type:
                r = await place_tool_adapter.search_places(
                    internal_category=llm_category, limit=50
                )
                venues = list(r.items)
        else:
            # LLM couldn't infer — try keyword search then broad fallback
            r = await place_tool_adapter.search_places(keyword=demand_text, limit=50)
            venues = list(r.items)
            if not venues:
                rest_r = await place_tool_adapter.search_places(internal_category="food", limit=50)
                attr_r = await place_tool_adapter.search_places(internal_category="attraction", limit=50)
                venues = list(rest_r.items) + list(attr_r.items)
    except Exception as exc:
        raise ValueError(f"candidates_error:data_service_unavailable:{exc}") from exc

    visited_ids = {str(vs.venue_id) for vs in session.visited_stops}
    venues = [v for v in venues if str(getattr(v, "venue_id", "")) not in visited_ids]

    # If visited-filter wiped everything, fall back with same category preference
    if not venues:
        try:
            category_fallback = llm_category or "food"
            r = await place_tool_adapter.search_places(internal_category=category_fallback, limit=50)
            venues = [v for v in r.items if str(getattr(v, "venue_id", "")) not in visited_ids]
            if not venues:
                rest_r = await place_tool_adapter.search_places(internal_category="food", limit=50)
                attr_r = await place_tool_adapter.search_places(internal_category="attraction", limit=50)
                venues = [v for v in list(rest_r.items) + list(attr_r.items)
                          if str(getattr(v, "venue_id", "")) not in visited_ids]
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

    session.reachable_cache = ReachableCache(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        venue_ids=[c.venue_id for c in cards],
        expires_at=datetime.now(UTC) + timedelta(minutes=_CACHE_TTL_MINUTES),
    )
    session.last_candidate_ids = [c.venue_id for c in cards]

    return cards, fallback_reason


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
        if cat not in _VALID_CATEGORIES:
            cat = None
        if not isinstance(pt, str) or not pt:
            pt = None
        return cat, pt
    except Exception as exc:
        logger.warning("_llm_parse_demand failed: %s", exc)
        return None, None


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
