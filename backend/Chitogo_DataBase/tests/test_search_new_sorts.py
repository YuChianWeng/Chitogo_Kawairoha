from __future__ import annotations

import unittest

from tests.direct_api_client import DirectApiClient
from tests.place_api_test_support import (
    FakeSession,
    build_feature,
    build_place,
)


class SearchNewSortsTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession(
            places=[
                build_place(
                    place_id=1,
                    google_place_id="gp-1",
                    display_name="Social Favorite",
                    district="中正區",
                    internal_category="food",
                    vibe_tags=["hidden_gem", "cozy"],
                    mention_count=9,
                    sentiment_score=0.65,
                    trend_score=0.90,
                    rating=4.4,
                ),
                build_place(
                    place_id=2,
                    google_place_id="gp-2",
                    display_name="Steady Brunch",
                    district="大安區",
                    internal_category="food",
                    vibe_tags=["brunch"],
                    mention_count=12,
                    sentiment_score=0.40,
                    trend_score=0.35,
                    rating=4.7,
                ),
                build_place(
                    place_id=3,
                    google_place_id="gp-3",
                    display_name="Hyped Night Market",
                    district="信義區",
                    internal_category="nightlife",
                    vibe_tags=["lively"],
                    mention_count=7,
                    sentiment_score=0.92,
                    trend_score=0.72,
                    rating=4.2,
                ),
                build_place(
                    place_id=4,
                    google_place_id="gp-4",
                    display_name="Unscored New Spot",
                    district="松山區",
                    internal_category="food",
                    vibe_tags=None,
                    mention_count=0,
                    sentiment_score=None,
                    trend_score=None,
                    rating=4.9,
                ),
            ],
            features=[
                build_feature(place_id=1, crowd_score=0.25),
                build_feature(place_id=2, crowd_score=0.80),
            ],
        )
        self.client = DirectApiClient(self.session)

    def test_search_supports_new_social_sort_modes(self):
        mention_response = self.client.get(
            "/api/v1/places/search",
            params={"sort": "mention_count_desc"},
        )
        trend_response = self.client.get(
            "/api/v1/places/search",
            params={"sort": "trend_score_desc"},
        )
        sentiment_response = self.client.get(
            "/api/v1/places/search",
            params={"sort": "sentiment_desc"},
        )

        self.assertEqual(
            [item["id"] for item in mention_response.json()["items"]],
            [2, 1, 3, 4],
        )
        self.assertEqual(
            [item["id"] for item in trend_response.json()["items"]],
            [1, 3, 2, 4],
        )
        self.assertEqual(
            [item["id"] for item in sentiment_response.json()["items"]],
            [3, 1, 2, 4],
        )

    def test_search_serializes_social_summary_and_crowd_score(self):
        response = self.client.get(
            "/api/v1/places/search",
            params={"sort": "mention_count_desc"},
        )

        self.assertEqual(response.status_code, 200)
        first_item = response.json()["items"][0]
        self.assertEqual(first_item["id"], 2)
        self.assertEqual(first_item["vibe_tags"], ["brunch"])
        self.assertEqual(first_item["mention_count"], 12)
        self.assertAlmostEqual(first_item["sentiment_score"], 0.4)
        self.assertAlmostEqual(first_item["trend_score"], 0.35)
        self.assertAlmostEqual(first_item["crowd_score"], 0.8)

    def test_recommend_serializes_social_summary_and_crowd_score(self):
        response = self.client.post("/api/v1/places/recommend", json={})

        self.assertEqual(response.status_code, 200)
        item = next(entry for entry in response.json()["items"] if entry["id"] == 1)
        self.assertEqual(item["vibe_tags"], ["hidden_gem", "cozy"])
        self.assertEqual(item["mention_count"], 9)
        self.assertAlmostEqual(item["sentiment_score"], 0.65)
        self.assertAlmostEqual(item["trend_score"], 0.9)
        self.assertAlmostEqual(item["crowd_score"], 0.25)


if __name__ == "__main__":
    unittest.main()
