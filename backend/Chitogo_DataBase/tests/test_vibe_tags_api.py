from __future__ import annotations

import unittest

from tests.direct_api_client import DirectApiClient
from tests.place_api_test_support import FakeSession, build_place


class VibeTagsApiTests(unittest.TestCase):
    def setUp(self):
        places = [
            build_place(
                place_id=1,
                google_place_id="gp-1",
                display_name="Riverside Date Spot",
                district="信義區",
                internal_category="food",
                primary_type="restaurant",
                vibe_tags=["romantic", "scenic"],
                mention_count=5,
            ),
            build_place(
                place_id=2,
                google_place_id="gp-2",
                display_name="Couple Cafe",
                district="信義區",
                internal_category="food",
                primary_type="cafe",
                vibe_tags=["romantic"],
                mention_count=3,
            ),
            build_place(
                place_id=3,
                google_place_id="gp-3",
                display_name="Daan Forest Lawn",
                district="大安區",
                internal_category="attraction",
                primary_type="park",
                vibe_tags=["scenic", "quiet"],
                mention_count=2,
            ),
            build_place(
                place_id=4,
                google_place_id="gp-4",
                display_name="Japanese Date Table",
                district="大安區",
                internal_category="food",
                primary_type="japanese_restaurant",
                vibe_tags=["romantic", "quiet"],
                mention_count=10,
            ),
            build_place(
                place_id=5,
                google_place_id="gp-5",
                display_name="No Social Tags",
                district="信義區",
                internal_category="shopping",
                primary_type="shopping_mall",
                vibe_tags=None,
                mention_count=7,
            ),
        ]
        places[3].types_json = ["japanese_restaurant", "restaurant"]

        self.client = DirectApiClient(FakeSession(places=places))

    def test_unfiltered_catalog_aggregates_and_sorts_distinct_tags(self):
        response = self.client.get("/api/v1/places/vibe-tags")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {"tag": "romantic", "place_count": 3, "mention_count": 18},
                    {"tag": "quiet", "place_count": 2, "mention_count": 12},
                    {"tag": "scenic", "place_count": 2, "mention_count": 7},
                ],
                "limit": 50,
                "scope": {
                    "district": None,
                    "internal_category": None,
                    "primary_type": None,
                },
            },
        )

    def test_district_scoped_catalog(self):
        response = self.client.get(
            "/api/v1/places/vibe-tags",
            params={"district": "信義區"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["items"],
            [
                {"tag": "romantic", "place_count": 2, "mention_count": 8},
                {"tag": "scenic", "place_count": 1, "mention_count": 5},
            ],
        )
        self.assertEqual(body["scope"]["district"], "信義區")

    def test_category_scoped_catalog(self):
        response = self.client.get(
            "/api/v1/places/vibe-tags",
            params={"internal_category": "food", "limit": 2},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["items"],
            [
                {"tag": "romantic", "place_count": 3, "mention_count": 18},
                {"tag": "quiet", "place_count": 1, "mention_count": 10},
            ],
        )
        self.assertEqual(body["limit"], 2)
        self.assertEqual(body["scope"]["internal_category"], "food")

    def test_primary_type_scoped_catalog_matches_primary_or_types_json(self):
        response = self.client.get(
            "/api/v1/places/vibe-tags",
            params={"primary_type": "restaurant"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"],
            [
                {"tag": "romantic", "place_count": 2, "mention_count": 15},
                {"tag": "quiet", "place_count": 1, "mention_count": 10},
                {"tag": "scenic", "place_count": 1, "mention_count": 5},
            ],
        )

    def test_empty_catalog_and_validation(self):
        empty_response = self.client.get(
            "/api/v1/places/vibe-tags",
            params={"district": "不存在"},
        )
        self.assertEqual(empty_response.status_code, 200)
        self.assertEqual(empty_response.json()["items"], [])

        invalid_category = self.client.get(
            "/api/v1/places/vibe-tags",
            params={"internal_category": "museum"},
        )
        self.assertEqual(invalid_category.status_code, 422)

        invalid_limit = self.client.get(
            "/api/v1/places/vibe-tags",
            params={"limit": 201},
        )
        self.assertEqual(invalid_limit.status_code, 422)


if __name__ == "__main__":
    unittest.main()
