from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.sql import operators

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from app.models.place_social_mention import PlaceSocialMention


def build_place(
    *,
    place_id: int,
    google_place_id: str,
    display_name: str,
    district: str,
    internal_category: str = "other",
    primary_type: str | None = "restaurant",
    rating: float | None = None,
    user_rating_count: int | None = None,
    budget_level: str | None = None,
    vibe_tags: list[str] | None = None,
    mention_count: int | None = None,
    sentiment_score: float | None = None,
    trend_score: float | None = None,
) -> Place:
    return Place(
        id=place_id,
        google_place_id=google_place_id,
        display_name=display_name,
        normalized_name=display_name.casefold(),
        primary_type=primary_type,
        types_json=[primary_type] if primary_type else None,
        formatted_address=f"Taipei {district}",
        district=district,
        latitude=Decimal("25.0000000"),
        longitude=Decimal("121.5000000"),
        rating=Decimal(str(rating)) if rating is not None else None,
        user_rating_count=user_rating_count,
        price_level=budget_level,
        budget_level=budget_level,
        internal_category=internal_category,
        vibe_tags=vibe_tags,
        mention_count=mention_count,
        sentiment_score=(
            Decimal(str(sentiment_score)) if sentiment_score is not None else None
        ),
        trend_score=Decimal(str(trend_score)) if trend_score is not None else None,
        indoor=True,
        outdoor=False,
        business_status="OPERATIONAL",
        google_maps_uri=f"https://maps.google.com/?cid={google_place_id}",
        created_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )


def build_feature(*, place_id: int, crowd_score: float | None = None) -> PlaceFeatures:
    return PlaceFeatures(
        place_id=place_id,
        crowd_score=Decimal(str(crowd_score)) if crowd_score is not None else None,
        updated_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )


def build_mention(
    *,
    mention_id: int,
    place_id: int,
    platform: str,
    external_id: str,
    posted_at: datetime | None,
    original_text: str | None = None,
    source_url: str | None = None,
    sentiment_score: float | None = None,
    crowdedness: float | None = None,
    vibe_tags: list[str] | None = None,
) -> PlaceSocialMention:
    return PlaceSocialMention(
        id=mention_id,
        place_id=place_id,
        platform=platform,
        external_id=external_id,
        posted_at=posted_at,
        original_text=original_text,
        source_url=source_url,
        sentiment_score=(
            Decimal(str(sentiment_score)) if sentiment_score is not None else None
        ),
        crowdedness=Decimal(str(crowdedness)) if crowdedness is not None else None,
        vibe_tags=vibe_tags,
    )


class FakeQuery:
    def __init__(self, items: list[object]):
        self.items = list(items)

    def filter(self, *conditions):
        filtered = self.items
        for condition in conditions:
            filtered = [item for item in filtered if _matches_condition(item, condition)]
        return FakeQuery(filtered)

    def offset(self, value: int):
        return FakeQuery(self.items[value:])

    def limit(self, value: int):
        return FakeQuery(self.items[:value])

    def all(self):
        return list(self.items)

    def count(self):
        return len(self.items)

    def order_by(self, *orderings):
        ordered = list(self.items)
        for ordering in reversed(orderings):
            field_name = _ordering_field_name(ordering)
            reverse = _ordering_is_desc(ordering)
            non_null_items = [
                item for item in ordered if getattr(item, field_name) is not None
            ]
            null_items = [
                item for item in ordered if getattr(item, field_name) is None
            ]
            non_null_items.sort(key=lambda item: getattr(item, field_name), reverse=reverse)
            ordered = non_null_items + null_items
        return FakeQuery(ordered)

    def first(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(
        self,
        *,
        places: list[Place],
        features: list[PlaceFeatures] | None = None,
        mentions: list[PlaceSocialMention] | None = None,
    ):
        self.places = list(places)
        self.features = list(features or [])
        self.mentions = list(mentions or [])

    def query(self, model):
        if model is Place:
            return FakeQuery(self.places)
        if model is PlaceFeatures:
            return FakeQuery(self.features)
        if model is PlaceSocialMention:
            return FakeQuery(self.mentions)
        raise AssertionError(f"Unexpected model queried: {model}")

    def close(self):
        return None


def _matches_condition(item: object, condition) -> bool:
    clauses = getattr(condition, "clauses", None)
    if clauses is not None and condition.operator == operators.or_:
        return any(_matches_condition(item, clause) for clause in clauses)

    left = condition.left
    right = condition.right
    operator = condition.operator
    field_name = getattr(left, "key", None) or getattr(left, "name", None)
    actual_value = getattr(item, field_name)
    expected_value = getattr(right, "value", right)

    if operator == operators.eq:
        return actual_value == expected_value
    if operator == operators.ge:
        return actual_value is not None and actual_value >= expected_value
    if operator == operators.ilike_op:
        needle = str(expected_value).strip("%").casefold()
        return needle in (actual_value or "").casefold()
    if operator == operators.in_op:
        return actual_value in expected_value
    if getattr(operator, "opstring", None) == "@>":
        if isinstance(actual_value, list) and isinstance(expected_value, list):
            return all(value in actual_value for value in expected_value)
        if isinstance(actual_value, dict) and isinstance(expected_value, dict):
            return all(
                actual_value.get(key) == value for key, value in expected_value.items()
            )
        return False

    is_null_comparison = getattr(right, "__visit_name__", None) == "null"
    if operator == operators.is_:
        if is_null_comparison:
            return actual_value is None
        return actual_value is expected_value
    if operator == operators.is_not:
        if is_null_comparison:
            return actual_value is not None
        return actual_value is not expected_value

    raise AssertionError(f"Unsupported filter operator in test fake query: {operator}")


def _ordering_field_name(ordering) -> str | None:
    current = ordering
    while current is not None:
        if getattr(current, "key", None) is not None:
            return current.key
        if getattr(current, "name", None) is not None:
            return current.name
        current = getattr(current, "element", None)
    return None


def _ordering_is_desc(ordering) -> bool:
    current = ordering
    while current is not None:
        if getattr(current, "modifier", None) == operators.desc_op:
            return True
        current = getattr(current, "element", None)
    return False
