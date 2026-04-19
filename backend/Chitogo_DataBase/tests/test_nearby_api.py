from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.sql import operators

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from tests.direct_api_client import DirectApiClient


def _make_place(
    *,
    place_id: int,
    google_place_id: str,
    display_name: str,
    primary_type: str | None,
    district: str | None,
    internal_category: str,
    latitude: float | None,
    longitude: float | None,
    rating: float | None = None,
    user_rating_count: int | None = 100,
    budget_level: str | None = None,
) -> Place:
    return Place(
        id=place_id,
        google_place_id=google_place_id,
        display_name=display_name,
        normalized_name=display_name.casefold(),
        primary_type=primary_type,
        types_json=[primary_type] if primary_type else None,
        formatted_address=f"Taipei {district}" if district else "Taipei",
        district=district,
        latitude=Decimal(str(latitude)) if latitude is not None else None,
        longitude=Decimal(str(longitude)) if longitude is not None else None,
        rating=Decimal(str(rating)) if rating is not None else None,
        user_rating_count=user_rating_count,
        price_level=budget_level,
        budget_level=budget_level,
        business_status="OPERATIONAL",
        google_maps_uri=f"https://maps.google.com/?cid={google_place_id}",
        website_uri=None,
        national_phone_number=None,
        opening_hours_json=None,
        indoor=True,
        outdoor=False,
        internal_category=internal_category,
        trend_score=Decimal("0.5000"),
        confidence_score=Decimal("0.9000"),
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        last_synced_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


class FakeQuery:
    def __init__(self, items: list[object]):
        self.items = list(items)

    def filter(self, *conditions):
        filtered = self.items
        for condition in conditions:
            filtered = [item for item in filtered if _matches_condition(item, condition)]
        return FakeQuery(filtered)

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
            non_null_items.sort(
                key=lambda item: getattr(item, field_name), reverse=reverse
            )
            ordered = non_null_items + null_items
        return FakeQuery(ordered)

    def offset(self, value: int):
        return FakeQuery(self.items[value:])

    def limit(self, value: int):
        return FakeQuery(self.items[:value])

    def all(self):
        return list(self.items)

    def count(self):
        return len(self.items)

    def first(self):
        return self.items[0] if self.items else None


class FakeAggregateQuery:
    def __init__(self, items: list[Place], group_field: str | None = None):
        self.items = list(items)
        self.group_field = group_field

    def filter(self, *conditions):
        filtered = self.items
        for condition in conditions:
            filtered = [item for item in filtered if _matches_condition(item, condition)]
        return FakeAggregateQuery(filtered, self.group_field)

    def group_by(self, *fields):
        if not fields:
            return self
        field_name = getattr(fields[0], "key", None) or getattr(fields[0], "name", None)
        return FakeAggregateQuery(self.items, field_name)

    def order_by(self, *orderings):
        return self

    def all(self):
        if self.group_field is None:
            raise AssertionError("Aggregate query requires group_by in test fake query")

        counts: dict[object, int] = {}
        for item in self.items:
            key = getattr(item, self.group_field)
            counts[key] = counts.get(key, 0) + 1

        rows = list(counts.items())
        rows.sort(key=lambda row: (-row[1], str(row[0])))
        return rows


class FakeSession:
    def __init__(self, places_data: list[Place], features_data: list[PlaceFeatures]):
        self.places_data = places_data
        self.features_data = features_data

    def query(self, *entities):
        if len(entities) == 1:
            if entities[0] is Place:
                return FakeQuery(self.places_data)
            if entities[0] is PlaceFeatures:
                return FakeQuery(self.features_data)

        return FakeAggregateQuery(self.places_data)

    def close(self):
        return None


def _matches_condition(item: object, condition) -> bool:
    left = condition.left
    right = condition.right
    operator = condition.operator
    field_name = getattr(left, "key", None) or getattr(left, "name", None)
    actual_value = getattr(item, field_name)
    expected_value = getattr(right, "value", right)
    is_null_comparison = getattr(right, "__visit_name__", None) == "null"

    if operator == operators.eq:
        return actual_value == expected_value
    if operator == operators.ge:
        return actual_value is not None and actual_value >= expected_value
    if operator == operators.le:
        return actual_value is not None and actual_value <= expected_value
    if operator == operators.ilike_op:
        needle = str(expected_value).strip("%").casefold()
        return needle in (actual_value or "").casefold()
    if operator == operators.in_op:
        return actual_value in expected_value
    if operator == operators.is_:
        if is_null_comparison:
            return actual_value is None
        return actual_value is expected_value
    if operator == operators.is_not:
        if is_null_comparison:
            return actual_value is not None
        return actual_value is not expected_value

    raise AssertionError(f"Unsupported filter operator in test fake query: {operator}")


def _ordering_field_name(ordering) -> str:
    current = ordering
    while current is not None:
        if getattr(current, "key", None) is not None:
            return current.key
        if getattr(current, "name", None) is not None:
            return current.name
        current = getattr(current, "element", None)
    raise AssertionError(f"Unsupported ordering expression: {ordering}")


def _ordering_is_desc(ordering) -> bool:
    current = ordering
    while current is not None:
        if getattr(current, "modifier", None) == operators.desc_op:
            return True
        current = getattr(current, "element", None)
    return False


class NearbyApiTests(unittest.TestCase):
    def setUp(self):
        self.center_lat = 25.0478
        self.center_lng = 121.5319
        self.places = [
            _make_place(
                place_id=1,
                google_place_id="gp-1",
                display_name="North Gate Hall",
                primary_type="tourist_attraction",
                district="中正區",
                internal_category="attraction",
                latitude=25.0479,
                longitude=121.5320,
                rating=4.8,
                user_rating_count=80,
                budget_level="PRICE_LEVEL_FREE",
            ),
            _make_place(
                place_id=2,
                google_place_id="gp-2",
                display_name="Civic Cafe",
                primary_type="cafe",
                district="中正區",
                internal_category="food",
                latitude=25.0485,
                longitude=121.5335,
                rating=4.6,
                user_rating_count=600,
                budget_level="INEXPENSIVE",
            ),
            _make_place(
                place_id=3,
                google_place_id="gp-3",
                display_name="Station Hotel",
                primary_type="hotel",
                district="中正區",
                internal_category="lodging",
                latitude=25.0515,
                longitude=121.5360,
                rating=4.2,
                user_rating_count=50,
                budget_level="EXPENSIVE",
            ),
            _make_place(
                place_id=4,
                google_place_id="gp-4",
                display_name="Market Basement",
                primary_type="shopping_mall",
                district="中正區",
                internal_category="shopping",
                latitude=25.0487,
                longitude=121.5324,
                rating=None,
                user_rating_count=10,
                budget_level=None,
            ),
            _make_place(
                place_id=5,
                google_place_id="gp-5",
                display_name="Riverside Cafe",
                primary_type="cafe",
                district="大同區",
                internal_category="food",
                latitude=25.0600,
                longitude=121.5600,
                rating=4.9,
                user_rating_count=900,
                budget_level="MODERATE",
            ),
            _make_place(
                place_id=6,
                google_place_id="gp-6",
                display_name="No Coordinate Place",
                primary_type="cafe",
                district="中正區",
                internal_category="food",
                latitude=None,
                longitude=None,
                rating=4.1,
                user_rating_count=20,
                budget_level="INEXPENSIVE",
            ),
        ]
        self.features = [
            PlaceFeatures(
                place_id=1,
                couple_score=Decimal("0.9"),
                updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            )
        ]
        self.session = FakeSession(self.places, self.features)
        self.client = DirectApiClient(self.session)

    def test_nearby_returns_places_within_radius_and_default_distance_sort(self):
        response = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["limit"], 20)
        self.assertEqual([item["id"] for item in body["items"]], [1, 4, 2, 3])
        self.assertTrue(all(item["distance_m"] <= 700 for item in body["items"]))
        self.assertLessEqual(body["items"][0]["distance_m"], body["items"][1]["distance_m"])

        limited = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
                "limit": 2,
            },
        )
        self.assertEqual(limited.status_code, 200)
        self.assertEqual(limited.json()["total"], 4)
        self.assertEqual(len(limited.json()["items"]), 2)
        self.assertEqual([item["id"] for item in limited.json()["items"]], [1, 4])

    def test_nearby_supports_filters_and_alternate_sorts(self):
        category = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
                "internal_category": "attraction",
            },
        )
        self.assertEqual([item["id"] for item in category.json()["items"]], [1])

        primary_type = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
                "primary_type": "cafe",
            },
        )
        self.assertEqual([item["id"] for item in primary_type.json()["items"]], [2])

        min_rating = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
                "min_rating": 4.5,
            },
        )
        self.assertEqual([item["id"] for item in min_rating.json()["items"]], [1, 2])

        max_budget = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
                "max_budget_level": 1,
            },
        )
        self.assertEqual([item["id"] for item in max_budget.json()["items"]], [1, 2])

        by_rating = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
                "sort": "rating_desc",
            },
        )
        self.assertEqual([item["id"] for item in by_rating.json()["items"]], [1, 2, 3, 4])

        by_user_count = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 700,
                "sort": "user_rating_count_desc",
            },
        )
        self.assertEqual([item["id"] for item in by_user_count.json()["items"]], [2, 1, 3, 4])

    def test_nearby_validation_and_empty_results(self):
        missing_lat = self.client.get(
            "/api/v1/places/nearby",
            params={"lng": self.center_lng, "radius_m": 500},
        )
        self.assertEqual(missing_lat.status_code, 422)

        missing_lng = self.client.get(
            "/api/v1/places/nearby",
            params={"lat": self.center_lat, "radius_m": 500},
        )
        self.assertEqual(missing_lng.status_code, 422)

        missing_radius = self.client.get(
            "/api/v1/places/nearby",
            params={"lat": self.center_lat, "lng": self.center_lng},
        )
        self.assertEqual(missing_radius.status_code, 422)

        invalid_lat = self.client.get(
            "/api/v1/places/nearby",
            params={"lat": 999, "lng": self.center_lng, "radius_m": 500},
        )
        self.assertEqual(invalid_lat.status_code, 422)

        invalid_lng = self.client.get(
            "/api/v1/places/nearby",
            params={"lat": self.center_lat, "lng": 999, "radius_m": 500},
        )
        self.assertEqual(invalid_lng.status_code, 422)

        invalid_radius = self.client.get(
            "/api/v1/places/nearby",
            params={"lat": self.center_lat, "lng": self.center_lng, "radius_m": 0},
        )
        self.assertEqual(invalid_radius.status_code, 422)

        too_large_radius = self.client.get(
            "/api/v1/places/nearby",
            params={"lat": self.center_lat, "lng": self.center_lng, "radius_m": 20000},
        )
        self.assertEqual(too_large_radius.status_code, 422)

        invalid_sort = self.client.get(
            "/api/v1/places/nearby",
            params={
                "lat": self.center_lat,
                "lng": self.center_lng,
                "radius_m": 500,
                "sort": "unknown_sort",
            },
        )
        self.assertEqual(invalid_sort.status_code, 422)

        no_results = self.client.get(
            "/api/v1/places/nearby",
            params={"lat": self.center_lat, "lng": self.center_lng, "radius_m": 5},
        )
        self.assertEqual(no_results.status_code, 200)
        self.assertEqual(no_results.json(), {"items": [], "total": 0, "limit": 20})

    def test_existing_endpoints_still_work(self):
        self.assertEqual(
            self.client.get("/api/v1/places", params={"limit": 2}).status_code, 200
        )
        self.assertEqual(self.client.get("/api/v1/places/1").status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/v1/places/search", params={"keyword": "Cafe", "limit": 5}
            ).status_code,
            200,
        )
        self.assertEqual(self.client.post("/api/v1/places/recommend", json={}).status_code, 200)
        self.assertEqual(
            self.client.post("/api/v1/places/batch", json={"place_ids": [1, 999]}).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/v1/places/stats").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/places/categories").status_code, 200)
