from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy.sql import operators

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from tests.direct_api_client import DirectApiClient


FIXED_NOW = datetime(2026, 4, 19, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _make_place(
    *,
    place_id: int,
    google_place_id: str,
    display_name: str,
    primary_type: str | None,
    district: str | None,
    rating: float | None,
    budget_level: str | None,
    internal_category: str,
    indoor: bool | None,
    user_rating_count: int = 100,
    opening_hours_json: dict | None = None,
) -> Place:
    return Place(
        id=place_id,
        google_place_id=google_place_id,
        display_name=display_name,
        normalized_name=display_name.casefold(),
        primary_type=primary_type,
        types_json=[primary_type] if primary_type else None,
        formatted_address=f"Taipei {district}" if district else None,
        district=district,
        latitude=Decimal("25.0000000"),
        longitude=Decimal("121.5000000"),
        rating=Decimal(str(rating)) if rating is not None else None,
        user_rating_count=user_rating_count,
        price_level=budget_level,
        budget_level=budget_level,
        internal_category=internal_category,
        indoor=indoor,
        outdoor=False if indoor is not None else None,
        business_status="OPERATIONAL",
        google_maps_uri=f"https://maps.google.com/?cid={google_place_id}",
        opening_hours_json=opening_hours_json,
        created_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )


def _open_period(day: int, open_hour: int, close_hour: int) -> dict:
    return {
        "periods": [
            {
                "open": {"day": day, "hour": open_hour, "minute": 0},
                "close": {"day": day, "hour": close_hour, "minute": 0},
            }
        ]
    }


class FakeQuery:
    def __init__(self, items: list[object]):
        self.items = list(items)

    def filter(self, *conditions):
        filtered = self.items
        for condition in conditions:
            filtered = [item for item in filtered if _matches_condition(item, condition)]
        return FakeQuery(filtered)

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

    def offset(self, value: int):
        return FakeQuery(self.items[value:])

    def limit(self, value: int):
        return FakeQuery(self.items[:value])

    def first(self):
        return self.items[0] if self.items else None


class FakeSession:
    def __init__(self, places_data: list[Place], features_data: list[PlaceFeatures]):
        self.places_data = places_data
        self.features_data = features_data

    def query(self, model):
        if model is Place:
            return FakeQuery(self.places_data)
        if model is PlaceFeatures:
            return FakeQuery(self.features_data)
        raise AssertionError(f"Unexpected model queried: {model}")

    def close(self):
        return None


def _matches_condition(item: object, condition) -> bool:
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
    if operator == operators.in_op:
        return actual_value in expected_value
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


class RecommendApiTests(unittest.TestCase):
    def setUp(self):
        self.places = [
            _make_place(
                place_id=1,
                google_place_id="gp-1",
                display_name="Feature Rich Attraction",
                primary_type="tourist_attraction",
                district="中正區",
                rating=4.2,
                budget_level="PRICE_LEVEL_FREE",
                internal_category="attraction",
                indoor=True,
                opening_hours_json=_open_period(0, 9, 18),
            ),
            _make_place(
                place_id=2,
                google_place_id="gp-2",
                display_name="Partial Feature Cafe",
                primary_type="cafe",
                district="大安區",
                rating=4.0,
                budget_level="INEXPENSIVE",
                internal_category="food",
                indoor=False,
                opening_hours_json=_open_period(0, 8, 20),
            ),
            _make_place(
                place_id=3,
                google_place_id="gp-3",
                display_name="Rating Only Hotel",
                primary_type="hotel",
                district="信義區",
                rating=4.8,
                budget_level="EXPENSIVE",
                internal_category="lodging",
                indoor=True,
                opening_hours_json=_open_period(0, 0, 23),
            ),
            _make_place(
                place_id=4,
                google_place_id="gp-4",
                display_name="No Signal Shop",
                primary_type="shopping_mall",
                district="中正區",
                rating=None,
                budget_level="MODERATE",
                internal_category="shopping",
                indoor=True,
                opening_hours_json=None,
            ),
            _make_place(
                place_id=5,
                google_place_id="gp-5",
                display_name="Transport Hub",
                primary_type="train_station",
                district="中正區",
                rating=5.0,
                budget_level="PRICE_LEVEL_FREE",
                internal_category="transport",
                indoor=True,
                opening_hours_json=_open_period(0, 0, 23),
            ),
            _make_place(
                place_id=6,
                google_place_id="gp-6",
                display_name="Night Bar",
                primary_type="bar",
                district="松山區",
                rating=4.6,
                budget_level="VERY_EXPENSIVE",
                internal_category="nightlife",
                indoor=True,
                opening_hours_json=None,
            ),
        ]
        self.features = [
            PlaceFeatures(
                place_id=1,
                couple_score=Decimal("0.9"),
                family_score=Decimal("0.7"),
                photo_score=Decimal("0.8"),
                updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
            PlaceFeatures(
                place_id=2,
                food_score=Decimal("0.6"),
                culture_score=Decimal("0.8"),
                updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
            PlaceFeatures(
                place_id=4,
                updated_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            ),
        ]
        self.session = FakeSession(self.places, self.features)
        self.client = DirectApiClient(self.session)

    def test_recommend_with_no_filters_uses_default_categories_and_descending_score(self):
        response = self.client.post("/api/v1/places/recommend", json={})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 4)
        self.assertEqual(body["limit"], 10)
        self.assertEqual(body["offset"], 0)
        self.assertEqual([item["id"] for item in body["items"]], [3, 1, 2, 4])
        self.assertNotIn(5, [item["id"] for item in body["items"]])
        self.assertNotIn(6, [item["id"] for item in body["items"]])

    def test_recommend_filters_districts_category_rating_budget_and_indoor(self):
        one_district = self.client.post(
            "/api/v1/places/recommend", json={"districts": ["中正區"]}
        )
        self.assertEqual(
            {item["id"] for item in one_district.json()["items"]},
            {1, 4},
        )

        multiple_districts = self.client.post(
            "/api/v1/places/recommend", json={"districts": ["中正區", "信義區"]}
        )
        self.assertEqual(
            {item["id"] for item in multiple_districts.json()["items"]},
            {1, 3, 4},
        )

        category = self.client.post(
            "/api/v1/places/recommend", json={"internal_category": "food"}
        )
        self.assertEqual([item["id"] for item in category.json()["items"]], [2])

        min_rating = self.client.post(
            "/api/v1/places/recommend", json={"min_rating": 4.5}
        )
        self.assertEqual([item["id"] for item in min_rating.json()["items"]], [3])

        max_budget = self.client.post(
            "/api/v1/places/recommend", json={"max_budget_level": 1}
        )
        self.assertEqual(
            {item["id"] for item in max_budget.json()["items"]},
            {1, 2},
        )

        indoor = self.client.post(
            "/api/v1/places/recommend", json={"indoor": False}
        )
        self.assertEqual([item["id"] for item in indoor.json()["items"]], [2])

    def test_recommend_open_now_and_limit(self):
        with patch(
            "app.services.place_recommendation.get_current_taipei_time",
            return_value=FIXED_NOW,
        ):
            open_now = self.client.post(
                "/api/v1/places/recommend", json={"open_now": True}
            )

        self.assertEqual(open_now.status_code, 200)
        self.assertEqual([item["id"] for item in open_now.json()["items"]], [3, 1, 2])
        self.assertEqual(open_now.json()["total"], 3)

        limited = self.client.post(
            "/api/v1/places/recommend", json={"limit": 2}
        )
        self.assertEqual([item["id"] for item in limited.json()["items"]], [3, 1])
        self.assertEqual(limited.json()["total"], 4)

    def test_recommend_scoring_cases(self):
        response = self.client.post("/api/v1/places/recommend", json={})
        body = response.json()
        items_by_id = {item["id"]: item for item in body["items"]}

        self.assertAlmostEqual(items_by_id[1]["recommendation_score"], 0.8)
        self.assertAlmostEqual(items_by_id[2]["recommendation_score"], 0.7)
        self.assertAlmostEqual(items_by_id[3]["recommendation_score"], 4.8)
        self.assertAlmostEqual(items_by_id[4]["recommendation_score"], 0.0)

    def test_recommend_validation_and_empty_result_edges(self):
        invalid_category = self.client.post(
            "/api/v1/places/recommend", json={"internal_category": "museum"}
        )
        self.assertEqual(invalid_category.status_code, 422)

        invalid_budget = self.client.post(
            "/api/v1/places/recommend", json={"max_budget_level": 5}
        )
        self.assertEqual(invalid_budget.status_code, 422)

        invalid_limit = self.client.post(
            "/api/v1/places/recommend", json={"limit": 0}
        )
        self.assertEqual(invalid_limit.status_code, 422)

        empty = self.client.post(
            "/api/v1/places/recommend", json={"districts": ["不存在區"]}
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), {"items": [], "total": 0, "limit": 10, "offset": 0})

    def test_existing_search_places_and_detail_endpoints_still_work(self):
        search_response = self.client.get("/api/v1/places/search")
        self.assertEqual(search_response.status_code, 200)

        list_response = self.client.get("/api/v1/places")
        self.assertEqual(list_response.status_code, 200)

        detail_response = self.client.get("/api/v1/places/1")
        self.assertEqual(detail_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
