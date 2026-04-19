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


FIXED_NOW = datetime(2026, 4, 18, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _make_place(
    *,
    place_id: int,
    google_place_id: str,
    display_name: str,
    primary_type: str | None,
    district: str | None,
    rating: float | None,
    user_rating_count: int | None,
    price_level: str | None,
    budget_level: str | None,
    internal_category: str,
    indoor: bool | None,
    latitude: float = 25.0,
    longitude: float = 121.5,
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
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        rating=Decimal(str(rating)) if rating is not None else None,
        user_rating_count=user_rating_count,
        price_level=price_level,
        budget_level=budget_level,
        internal_category=internal_category,
        indoor=indoor,
        outdoor=False if indoor is not None else None,
        business_status="OPERATIONAL",
        google_maps_uri=f"https://maps.google.com/?cid={google_place_id}",
        opening_hours_json=opening_hours_json,
        created_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
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
            if field_name is None:
                raise AssertionError(f"Unsupported ordering expression in test fake query: {ordering}")
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
    if operator == operators.ilike_op:
        needle = str(expected_value).strip("%").casefold()
        return needle in (actual_value or "").casefold()
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


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.places = [
            _make_place(
                place_id=1,
                google_place_id="gp-1",
                display_name="Huashan Creative Park",
                primary_type="tourist_attraction",
                district="中正區",
                rating=4.8,
                user_rating_count=500,
                price_level="PRICE_LEVEL_FREE",
                budget_level="PRICE_LEVEL_FREE",
                internal_category="attraction",
                indoor=True,
                opening_hours_json=_open_period(6, 9, 18),
            ),
            _make_place(
                place_id=2,
                google_place_id="gp-2",
                display_name="Daan Brunch Cafe",
                primary_type="cafe",
                district="大安區",
                rating=4.5,
                user_rating_count=900,
                price_level="INEXPENSIVE",
                budget_level="INEXPENSIVE",
                internal_category="food",
                indoor=False,
                opening_hours_json=_open_period(6, 18, 23),
            ),
            _make_place(
                place_id=3,
                google_place_id="gp-3",
                display_name="Quiet Coffee Lab",
                primary_type="cafe",
                district="大安區",
                rating=None,
                user_rating_count=50,
                price_level=None,
                budget_level=None,
                internal_category="food",
                indoor=True,
                opening_hours_json=None,
            ),
            _make_place(
                place_id=4,
                google_place_id="gp-4",
                display_name="Xinyi Grand Hotel",
                primary_type="hotel",
                district="信義區",
                rating=4.1,
                user_rating_count=200,
                price_level="EXPENSIVE",
                budget_level="EXPENSIVE",
                internal_category="lodging",
                indoor=True,
                opening_hours_json=_open_period(6, 0, 23),
            ),
            _make_place(
                place_id=5,
                google_place_id="gp-5",
                display_name="Underground Mall",
                primary_type="shopping_mall",
                district="中正區",
                rating=4.0,
                user_rating_count=1000,
                price_level="MODERATE",
                budget_level="MODERATE",
                internal_category="shopping",
                indoor=True,
                opening_hours_json=_open_period(6, 10, 21),
            ),
            _make_place(
                place_id=6,
                google_place_id="gp-6",
                display_name="Night Owl Bar",
                primary_type="bar",
                district="松山區",
                rating=4.7,
                user_rating_count=300,
                price_level="VERY_EXPENSIVE",
                budget_level="VERY_EXPENSIVE",
                internal_category="nightlife",
                indoor=True,
                opening_hours_json=None,
            ),
        ]
        self.features = [
            PlaceFeatures(
                place_id=1,
                couple_score=0.8,
                family_score=0.7,
                updated_at=datetime(2026, 4, 18, tzinfo=timezone.utc),
            )
        ]
        self.session = FakeSession(self.places, self.features)
        self.client = DirectApiClient(self.session)

    def test_search_with_no_filters_returns_sorted_results(self):
        response = self.client.get("/api/v1/places/search")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 6)
        self.assertEqual(body["limit"], 20)
        self.assertEqual(body["offset"], 0)
        self.assertEqual([item["id"] for item in body["items"][:3]], [1, 6, 2])

    def test_search_filters_cover_district_category_primary_type_and_keyword(self):
        district_response = self.client.get(
            "/api/v1/places/search", params={"district": "中正區"}
        )
        self.assertEqual(
            {item["id"] for item in district_response.json()["items"]},
            {1, 5},
        )

        category_response = self.client.get(
            "/api/v1/places/search", params={"internal_category": "food"}
        )
        self.assertEqual(
            {item["id"] for item in category_response.json()["items"]},
            {2, 3},
        )

        primary_type_response = self.client.get(
            "/api/v1/places/search", params={"primary_type": "hotel"}
        )
        self.assertEqual(
            [item["id"] for item in primary_type_response.json()["items"]],
            [4],
        )

        keyword_response = self.client.get(
            "/api/v1/places/search", params={"keyword": "cafe"}
        )
        self.assertEqual(
            [item["id"] for item in keyword_response.json()["items"]],
            [2],
        )

    def test_search_filters_cover_rating_budget_indoor_and_open_now(self):
        min_rating_response = self.client.get(
            "/api/v1/places/search", params={"min_rating": 4.5}
        )
        self.assertEqual(
            [item["id"] for item in min_rating_response.json()["items"]],
            [1, 6, 2],
        )

        budget_response = self.client.get(
            "/api/v1/places/search", params={"max_budget_level": 2}
        )
        self.assertEqual(
            {item["id"] for item in budget_response.json()["items"]},
            {1, 2, 5},
        )

        indoor_response = self.client.get(
            "/api/v1/places/search", params={"indoor": True}
        )
        self.assertEqual(
            {item["id"] for item in indoor_response.json()["items"]},
            {1, 3, 4, 5, 6},
        )

        with patch(
            "app.services.place_search.get_current_taipei_time",
            return_value=FIXED_NOW,
        ):
            open_now_response = self.client.get(
                "/api/v1/places/search", params={"open_now": True}
            )
            open_now_false_response = self.client.get(
                "/api/v1/places/search", params={"open_now": False}
            )

        self.assertEqual(
            {item["id"] for item in open_now_response.json()["items"]},
            {1, 4, 5},
        )
        self.assertEqual(open_now_response.json()["total"], 3)
        self.assertEqual(open_now_false_response.json()["total"], 6)

    def test_search_sort_and_pagination(self):
        rating_response = self.client.get(
            "/api/v1/places/search", params={"sort": "rating_desc"}
        )
        self.assertEqual(
            [item["id"] for item in rating_response.json()["items"][:4]],
            [1, 6, 2, 4],
        )

        count_response = self.client.get(
            "/api/v1/places/search", params={"sort": "user_rating_count_desc"}
        )
        self.assertEqual(
            [item["id"] for item in count_response.json()["items"][:4]],
            [5, 2, 1, 6],
        )

        page_response = self.client.get(
            "/api/v1/places/search", params={"limit": 2, "offset": 1}
        )
        self.assertEqual(page_response.json()["total"], 6)
        self.assertEqual([item["id"] for item in page_response.json()["items"]], [6, 2])

    def test_search_validation_and_empty_result_edges(self):
        invalid_sort = self.client.get(
            "/api/v1/places/search", params={"sort": "distance_asc"}
        )
        self.assertEqual(invalid_sort.status_code, 422)

        invalid_budget = self.client.get(
            "/api/v1/places/search", params={"max_budget_level": 5}
        )
        self.assertEqual(invalid_budget.status_code, 422)

        invalid_category = self.client.get(
            "/api/v1/places/search", params={"internal_category": "museum"}
        )
        self.assertEqual(invalid_category.status_code, 422)

        invalid_min_rating = self.client.get(
            "/api/v1/places/search", params={"min_rating": 5.5}
        )
        self.assertEqual(invalid_min_rating.status_code, 422)

        invalid_limit = self.client.get(
            "/api/v1/places/search", params={"limit": 0}
        )
        self.assertEqual(invalid_limit.status_code, 422)

        invalid_offset = self.client.get(
            "/api/v1/places/search", params={"offset": -1}
        )
        self.assertEqual(invalid_offset.status_code, 422)

        no_match = self.client.get(
            "/api/v1/places/search", params={"keyword": "no-such-place"}
        )
        self.assertEqual(no_match.status_code, 200)
        self.assertEqual(no_match.json(), {"items": [], "total": 0, "limit": 20, "offset": 0})

    def test_search_excludes_null_rating_and_null_budget_when_filters_are_active(self):
        min_rating_response = self.client.get(
            "/api/v1/places/search", params={"min_rating": 0}
        )
        self.assertNotIn(3, {item["id"] for item in min_rating_response.json()["items"]})

        budget_response = self.client.get(
            "/api/v1/places/search", params={"max_budget_level": 4}
        )
        self.assertNotIn(3, {item["id"] for item in budget_response.json()["items"]})

    def test_existing_list_and_detail_endpoints_still_work(self):
        list_response = self.client.get("/api/v1/places", params={"district": "中正區"})
        self.assertEqual(list_response.status_code, 200)
        list_items = list_response.json()
        self.assertEqual({item["id"] for item in list_items}, {1, 5})
        self.assertNotIn("internal_category", list_items[0])

        detail_response = self.client.get("/api/v1/places/1")
        self.assertEqual(detail_response.status_code, 200)
        detail_body = detail_response.json()
        self.assertEqual(detail_body["id"], 1)
        self.assertNotIn("internal_category", detail_body)
        self.assertIn("features", detail_body)
        self.assertEqual(detail_body["features"]["couple_score"], 0.8)


if __name__ == "__main__":
    unittest.main()
