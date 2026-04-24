from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.sql import operators

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from app.models.place_social_mention import PlaceSocialMention
from app.models.place_source_google import PlaceSourceGoogle


class FakeQuery:
    def __init__(self, items: list[object]):
        self.items = list(items)

    def filter(self, *conditions):
        filtered = self.items
        for condition in conditions:
            filtered = [item for item in filtered if _matches_condition(item, condition)]
        return FakeQuery(filtered)

    def filter_by(self, **kwargs):
        filtered = []
        for item in self.items:
            if all(getattr(item, key) == value for key, value in kwargs.items()):
                filtered.append(item)
        return FakeQuery(filtered)

    def all(self):
        return list(self.items)

    def first(self):
        return self.items[0] if self.items else None

    def count(self):
        return len(self.items)


class FakeSession:
    def __init__(
        self,
        *,
        places: list[Place] | None = None,
        features: list[PlaceFeatures] | None = None,
        mentions: list[PlaceSocialMention] | None = None,
        raw_records: list[PlaceSourceGoogle] | None = None,
    ):
        self.places = list(places or [])
        self.features = list(features or [])
        self.mentions = list(mentions or [])
        self.raw_records = list(raw_records or [])
        self._next_place_id = max((place.id or 0 for place in self.places), default=0) + 1
        self._next_mention_id = max(
            (mention.id or 0 for mention in self.mentions), default=0
        ) + 1
        self.query_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def query(self, model):
        self.query_count += 1
        if model is Place:
            return FakeQuery(self.places)
        if model is PlaceFeatures:
            return FakeQuery(self.features)
        if model is PlaceSocialMention:
            return FakeQuery(self.mentions)
        if model is PlaceSourceGoogle:
            return FakeQuery(self.raw_records)
        raise AssertionError(f"Unexpected model queried: {model}")

    def add(self, obj):
        if isinstance(obj, Place):
            if obj not in self.places:
                self.places.append(obj)
            return
        if isinstance(obj, PlaceFeatures):
            if obj not in self.features:
                self.features.append(obj)
            return
        if isinstance(obj, PlaceSocialMention):
            if obj not in self.mentions:
                self.mentions.append(obj)
            return
        if isinstance(obj, PlaceSourceGoogle):
            self.raw_records.append(obj)
            return
        raise AssertionError(f"Unexpected object added: {obj!r}")

    def flush(self):
        for place in self.places:
            if place.id is None:
                place.id = self._next_place_id
                self._next_place_id += 1
        for mention in self.mentions:
            if mention.id is None:
                mention.id = self._next_mention_id
                self._next_mention_id += 1

    def commit(self):
        self.commit_count += 1
        self.flush()
        return None

    def rollback(self):
        self.rollback_count += 1
        return None

    def refresh(self, _obj):
        return None

    def close(self):
        return None


def build_place(
    *,
    place_id: int | None,
    google_place_id: str,
    display_name: str,
    district: str,
    internal_category: str = "other",
    formatted_address: str | None = None,
) -> Place:
    return Place(
        id=place_id,
        google_place_id=google_place_id,
        display_name=display_name,
        normalized_name=display_name.casefold(),
        district=district,
        formatted_address=formatted_address or f"Taipei {district}",
        internal_category=internal_category,
        mention_count=0,
    )


def build_mention(
    *,
    mention_id: int | None,
    place_id: int,
    platform: str,
    external_id: str,
    sentiment_score: str | None = None,
    crowdedness: str | None = None,
    vibe_tags: list[str] | None = None,
    posted_at: datetime | None = None,
) -> PlaceSocialMention:
    return PlaceSocialMention(
        id=mention_id,
        place_id=place_id,
        platform=platform,
        external_id=external_id,
        sentiment_score=Decimal(sentiment_score) if sentiment_score is not None else None,
        crowdedness=Decimal(crowdedness) if crowdedness is not None else None,
        vibe_tags=vibe_tags,
        posted_at=posted_at,
    )


def build_google_payload(
    *,
    google_place_id: str,
    display_name: str,
    district: str,
    primary_type: str = "restaurant",
    types: list[str] | None = None,
    formatted_address: str | None = None,
) -> dict:
    return {
        "id": google_place_id,
        "displayName": {"text": display_name},
        "primaryType": primary_type,
        "types": types or [primary_type, "point_of_interest"],
        "formattedAddress": formatted_address or f"100台灣臺北市{district}測試路1號",
        "addressComponents": [
            {
                "longText": district,
                "types": ["administrative_area_level_2", "political"],
            }
        ],
        "location": {"latitude": 25.0, "longitude": 121.5},
        "rating": 4.5,
        "userRatingCount": 120,
        "businessStatus": "OPERATIONAL",
        "googleMapsUri": f"https://maps.google.com/?cid={google_place_id}",
        "regularOpeningHours": {"weekdayDescriptions": ["Mon: 09:00-18:00"]},
    }


def utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _matches_condition(item: object, condition) -> bool:
    left = condition.left
    right = condition.right
    operator = condition.operator
    field_name = getattr(left, "key", None) or getattr(left, "name", None)
    actual_value = getattr(item, field_name)
    expected_value = getattr(right, "value", right)

    if operator == operators.in_op:
        return actual_value in expected_value

    raise AssertionError(f"Unsupported filter operator in fake query: {operator}")
