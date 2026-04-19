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
    rating: float | None = None,
    user_rating_count: int | None = 100,
    budget_level: str | None = None,
    indoor: bool | None = True,
    opening_hours_json: dict | None = None,
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
        latitude=Decimal("25.0000000"),
        longitude=Decimal("121.5000000"),
        rating=Decimal(str(rating)) if rating is not None else None,
        user_rating_count=user_rating_count,
        price_level=budget_level,
        budget_level=budget_level,
        business_status="OPERATIONAL",
        google_maps_uri=f"https://maps.google.com/?cid={google_place_id}",
        website_uri=None,
        national_phone_number=None,
        opening_hours_json=opening_hours_json,
        indoor=indoor,
        outdoor=False if indoor is not None else None,
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
            non_null_items.sort(key=lambda item: getattr(item, field_name), reverse=reverse)
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


class BatchStatsApiTests(unittest.TestCase):
    def setUp(self):
        self.places = [
            _make_place(
                place_id=1,
                google_place_id="gp-1",
                display_name="Huashan Creative Park",
                primary_type="tourist_attraction",
                district="中正區",
                internal_category="attraction",
                rating=4.8,
                budget_level="PRICE_LEVEL_FREE",
            ),
            _make_place(
                place_id=2,
                google_place_id="gp-2",
                display_name="Daan Brunch Cafe",
                primary_type="cafe",
                district="大安區",
                internal_category="food",
                rating=4.5,
                budget_level="INEXPENSIVE",
            ),
            _make_place(
                place_id=3,
                google_place_id="gp-3",
                display_name="Xinyi Grand Hotel",
                primary_type="hotel",
                district="信義區",
                internal_category="lodging",
                rating=4.2,
                budget_level="EXPENSIVE",
            ),
            _make_place(
                place_id=4,
                google_place_id="gp-4",
                display_name="Mall Basement",
                primary_type="shopping_mall",
                district="中正區",
                internal_category="shopping",
                rating=4.0,
                budget_level="MODERATE",
            ),
            _make_place(
                place_id=5,
                google_place_id="gp-5",
                display_name="Mystery Corner",
                primary_type=None,
                district=None,
                internal_category="other",
                rating=None,
                budget_level=None,
                indoor=None,
            ),
        ]
        self.features = [
            PlaceFeatures(
                place_id=1,
                couple_score=Decimal("0.8"),
                transport_score=Decimal("0.6"),
                updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
            PlaceFeatures(
                place_id=3,
                family_score=Decimal("0.7"),
                feature_json={"note": "family-friendly"},
                updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
        ]
        self.session = FakeSession(self.places, self.features)
        self.client = DirectApiClient(self.session)

    def test_batch_returns_matching_places_in_input_order_with_detail_fields(self):
        response = self.client.post(
            "/api/v1/places/batch",
            json={"place_ids": [3, 999, 1, 3]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["id"] for item in body["items"]], [3, 1, 3])

        first_item = body["items"][0]
        self.assertEqual(first_item["internal_category"], "lodging")
        self.assertEqual(first_item["primary_type"], "hotel")
        self.assertEqual(first_item["types_json"], ["hotel"])
        self.assertEqual(first_item["district"], "信義區")
        self.assertEqual(first_item["budget_level"], "EXPENSIVE")
        self.assertIn("opening_hours_json", first_item)
        self.assertIn("trend_score", first_item)
        self.assertIn("confidence_score", first_item)
        self.assertEqual(first_item["features"]["family_score"], 0.7)

        second_item = body["items"][1]
        self.assertEqual(second_item["id"], 1)
        self.assertEqual(second_item["features"]["couple_score"], 0.8)

    def test_batch_validation_and_unknown_only_behavior(self):
        unknown_only = self.client.post(
            "/api/v1/places/batch",
            json={"place_ids": [9999]},
        )
        self.assertEqual(unknown_only.status_code, 200)
        self.assertEqual(unknown_only.json(), {"items": []})

        empty_ids = self.client.post("/api/v1/places/batch", json={"place_ids": []})
        self.assertEqual(empty_ids.status_code, 422)

        invalid_body = self.client.post(
            "/api/v1/places/batch",
            json={"place_ids": "not-a-list"},
        )
        self.assertEqual(invalid_body.status_code, 422)

        too_many_ids = self.client.post(
            "/api/v1/places/batch",
            json={"place_ids": list(range(1, 102))},
        )
        self.assertEqual(too_many_ids.status_code, 422)

    def test_stats_returns_total_and_grouped_counts(self):
        response = self.client.get("/api/v1/places/stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "total_places": 5,
                "by_district": {"中正區": 2, "大安區": 1, "信義區": 1},
                "by_internal_category": {
                    "attraction": 1,
                    "food": 1,
                    "lodging": 1,
                    "other": 1,
                    "shopping": 1,
                },
                "by_primary_type": {
                    "cafe": 1,
                    "hotel": 1,
                    "shopping_mall": 1,
                    "tourist_attraction": 1,
                },
            },
        )

    def test_existing_places_search_recommend_and_detail_endpoints_still_work(self):
        self.assertEqual(self.client.get("/api/v1/places").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/places/1").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/places/search").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/places/recommend", json={}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
