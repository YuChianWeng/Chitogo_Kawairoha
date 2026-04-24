from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from app.models.place_social_mention import PlaceSocialMention

TREND_HALF_LIFE_DAYS = 7
SENTIMENT_PRECISION = Decimal("0.01")
SCORE_PRECISION = Decimal("0.0001")
MIN_POSTED_AT = datetime.min.replace(tzinfo=timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _mean(values: list[Decimal], *, precision: Decimal) -> Decimal | None:
    if not values:
        return None
    total = sum(values, Decimal("0"))
    average = total / Decimal(len(values))
    return average.quantize(precision, rounding=ROUND_HALF_UP)


def _trend_weight(posted_at: datetime | None, now: datetime) -> float:
    if posted_at is None:
        return 1.0

    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    age_seconds = max((now - posted_at).total_seconds(), 0.0)
    age_days = age_seconds / 86400.0
    return math.pow(0.5, age_days / TREND_HALF_LIFE_DAYS)


def _datetime_sort_value(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp())


def _tag_sort_key(item: tuple[str, tuple[int, datetime]]) -> tuple[int, int, str]:
    tag, (count, latest_posted_at) = item
    return (-count, -_datetime_sort_value(latest_posted_at), tag)


def recompute_social_aggregates(
    db: Session, place_ids: Iterable[int] | None = None
) -> None:
    target_ids = {int(place_id) for place_id in place_ids or []}
    if place_ids is not None and not target_ids:
        return

    if target_ids:
        places = db.query(Place).filter(Place.id.in_(target_ids)).all()
        mentions = (
            db.query(PlaceSocialMention)
            .filter(PlaceSocialMention.place_id.in_(target_ids))
            .all()
        )
        features = (
            db.query(PlaceFeatures)
            .filter(PlaceFeatures.place_id.in_(target_ids))
            .all()
        )
    else:
        places = db.query(Place).all()
        mentions = db.query(PlaceSocialMention).all()
        features = db.query(PlaceFeatures).all()

    mentions_by_place: dict[int, list[PlaceSocialMention]] = defaultdict(list)
    for mention in mentions:
        mentions_by_place[mention.place_id].append(mention)

    feature_by_place_id = {feature.place_id: feature for feature in features}
    now = utc_now()

    raw_trend_scores: dict[int, float] = {}
    aggregates_by_place_id: dict[int, dict[str, object]] = {}

    for place in places:
        place_mentions = mentions_by_place.get(place.id, [])
        sentiment_values: list[Decimal] = []
        crowd_values: list[Decimal] = []
        tag_stats: dict[str, tuple[int, datetime]] = {}
        raw_trend = 0.0

        for mention in place_mentions:
            sentiment_value = _to_decimal(mention.sentiment_score)
            if sentiment_value is not None:
                sentiment_values.append(sentiment_value)

            crowd_value = _to_decimal(mention.crowdedness)
            if crowd_value is not None:
                crowd_values.append(crowd_value)

            posted_at = mention.posted_at
            if posted_at is None:
                latest_posted_at = MIN_POSTED_AT
            elif posted_at.tzinfo is None:
                latest_posted_at = posted_at.replace(tzinfo=timezone.utc)
            else:
                latest_posted_at = posted_at

            for tag in dict.fromkeys(mention.vibe_tags or []):
                count, previous_latest = tag_stats.get(tag, (0, MIN_POSTED_AT))
                tag_stats[tag] = (count + 1, max(previous_latest, latest_posted_at))

            raw_trend += _trend_weight(posted_at, now)

        raw_trend_scores[place.id] = raw_trend
        aggregates_by_place_id[place.id] = {
            "mention_count": len(place_mentions),
            "sentiment_score": _mean(
                sentiment_values, precision=SENTIMENT_PRECISION
            ),
            "crowd_score": _mean(crowd_values, precision=SCORE_PRECISION),
            "vibe_tags": [
                tag
                for tag, _stats in sorted(tag_stats.items(), key=_tag_sort_key)[:12]
            ]
            or None,
        }

    max_raw_trend = max(raw_trend_scores.values(), default=0.0)

    for place in places:
        aggregates = aggregates_by_place_id.get(place.id)
        if aggregates is None:
            continue

        place.mention_count = int(aggregates["mention_count"])
        place.sentiment_score = aggregates["sentiment_score"]
        place.vibe_tags = aggregates["vibe_tags"]

        raw_trend = raw_trend_scores.get(place.id, 0.0)
        if place.mention_count == 0 or max_raw_trend <= 0.0:
            place.trend_score = None
        else:
            normalized_trend = Decimal(f"{raw_trend / max_raw_trend:.4f}")
            place.trend_score = normalized_trend.quantize(
                SCORE_PRECISION, rounding=ROUND_HALF_UP
            )

        feature = feature_by_place_id.get(place.id)
        crowd_score = aggregates["crowd_score"]
        if feature is None:
            if crowd_score is not None:
                db.add(PlaceFeatures(place_id=place.id, crowd_score=crowd_score))
        else:
            feature.crowd_score = crowd_score

    db.commit()
