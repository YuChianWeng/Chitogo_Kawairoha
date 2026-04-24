from __future__ import annotations

import unittest

from tests.direct_api_client import DirectApiClient
from tests.place_api_test_support import FakeSession, build_place


class SearchVibeTagFilterTests(unittest.TestCase):
    def setUp(self):
        self.client = DirectApiClient(
            FakeSession(
                places=[
                    build_place(
                        place_id=1,
                        google_place_id="gp-1",
                        display_name="Riverside Date Spot",
                        district="大安區",
                        internal_category="food",
                        vibe_tags=["romantic", "scenic"],
                        mention_count=6,
                    ),
                    build_place(
                        place_id=2,
                        google_place_id="gp-2",
                        display_name="Couple Cafe",
                        district="大安區",
                        internal_category="food",
                        vibe_tags=["romantic"],
                        mention_count=4,
                    ),
                    build_place(
                        place_id=3,
                        google_place_id="gp-3",
                        display_name="Observation Deck",
                        district="信義區",
                        internal_category="attraction",
                        vibe_tags=["scenic"],
                        mention_count=5,
                    ),
                    build_place(
                        place_id=4,
                        google_place_id="gp-4",
                        display_name="Quiet Tea House",
                        district="中山區",
                        internal_category="food",
                        vibe_tags=["romantic", "quiet", "scenic"],
                        mention_count=1,
                    ),
                ]
            )
        )

    def test_repeated_vibe_tags_use_intersection_semantics(self):
        response = self.client.get(
            "/api/v1/places/search",
            params={"vibe_tag": ["romantic", "scenic"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["items"]],
            [1, 4],
        )

    def test_min_mentions_filters_after_vibe_tag_match(self):
        response = self.client.get(
            "/api/v1/places/search",
            params={"vibe_tag": ["romantic", "scenic"], "min_mentions": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["items"]],
            [1],
        )


if __name__ == "__main__":
    unittest.main()
