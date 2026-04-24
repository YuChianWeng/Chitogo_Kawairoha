from __future__ import annotations

import unittest
from datetime import datetime, timezone

from tests.direct_api_client import DirectApiClient
from tests.place_api_test_support import FakeSession, build_mention, build_place


class PlaceDetailRecentMentionsTests(unittest.TestCase):
    def setUp(self):
        self.client = DirectApiClient(
            FakeSession(
                places=[
                    build_place(
                        place_id=1,
                        google_place_id="gp-1",
                        display_name="Mentioned Place",
                        district="大安區",
                        internal_category="food",
                        vibe_tags=["cozy"],
                        mention_count=6,
                        sentiment_score=0.75,
                        trend_score=0.88,
                    )
                ],
                mentions=[
                    build_mention(
                        mention_id=1,
                        place_id=1,
                        platform="instagram",
                        external_id="ig-1",
                        posted_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
                        original_text="Newest mention",
                        source_url="https://example.com/ig-1",
                        vibe_tags=["cozy"],
                    ),
                    build_mention(
                        mention_id=2,
                        place_id=1,
                        platform="threads",
                        external_id="th-1",
                        posted_at=datetime(2026, 4, 19, 10, 0, tzinfo=timezone.utc),
                        original_text="Second newest",
                        source_url="https://example.com/th-1",
                    ),
                    build_mention(
                        mention_id=3,
                        place_id=1,
                        platform="reddit",
                        external_id="rd-1",
                        posted_at=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
                        original_text="Third newest",
                        source_url="https://example.com/rd-1",
                    ),
                    build_mention(
                        mention_id=4,
                        place_id=1,
                        platform="instagram",
                        external_id="ig-2",
                        posted_at=datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
                        original_text="Fourth newest",
                        source_url="https://example.com/ig-2",
                    ),
                    build_mention(
                        mention_id=5,
                        place_id=1,
                        platform="threads",
                        external_id="th-2",
                        posted_at=datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc),
                        original_text="Fifth newest",
                        source_url="https://example.com/th-2",
                    ),
                    build_mention(
                        mention_id=6,
                        place_id=1,
                        platform="reddit",
                        external_id="rd-2",
                        posted_at=None,
                        original_text="No timestamp",
                        source_url="https://example.com/rd-2",
                    ),
                ],
            )
        )

    def test_detail_returns_latest_five_mentions_in_descending_recency(self):
        response = self.client.get("/api/v1/places/1")

        self.assertEqual(response.status_code, 200)
        mentions = response.json()["recent_mentions"]
        self.assertEqual(len(mentions), 5)
        self.assertEqual(
            [mention["original_text"] for mention in mentions],
            [
                "Newest mention",
                "Second newest",
                "Third newest",
                "Fourth newest",
                "Fifth newest",
            ],
        )
        self.assertEqual(mentions[0]["platform"], "instagram")
        self.assertEqual(mentions[0]["vibe_tags"], ["cozy"])


if __name__ == "__main__":
    unittest.main()
