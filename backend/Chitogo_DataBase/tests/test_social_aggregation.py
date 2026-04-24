import unittest
from datetime import timezone
from decimal import Decimal
from unittest.mock import patch

from app.models.place_features import PlaceFeatures
from app.services.social_aggregation import recompute_social_aggregates
from tests.social_test_support import (
    FakeSession,
    build_mention,
    build_place,
    utc_datetime,
)


class SocialAggregationTests(unittest.TestCase):
    def test_recompute_returns_early_for_empty_place_ids(self):
        session = FakeSession()

        recompute_social_aggregates(session, place_ids=[])

        self.assertEqual(session.query_count, 0)
        self.assertEqual(session.commit_count, 0)

    def test_recompute_updates_place_fields_and_feature_scores(self):
        place_one = build_place(
            place_id=1,
            google_place_id="gp-1",
            display_name="Place One",
            district="中正區",
        )
        place_two = build_place(
            place_id=2,
            google_place_id="gp-2",
            display_name="Place Two",
            district="大安區",
        )
        session = FakeSession(
            places=[place_one, place_two],
            mentions=[
                build_mention(
                    mention_id=1,
                    place_id=1,
                    platform="threads",
                    external_id="m1",
                    sentiment_score="0.80",
                    crowdedness="0.25",
                    vibe_tags=["hidden_gem", "quiet"],
                    posted_at=utc_datetime(2026, 4, 23, 12, 0),
                ),
                build_mention(
                    mention_id=2,
                    place_id=1,
                    platform="threads",
                    external_id="m2",
                    sentiment_score="0.60",
                    crowdedness="0.75",
                    vibe_tags=["hidden_gem", "brunch"],
                    posted_at=utc_datetime(2026, 4, 22, 12, 0),
                ),
                build_mention(
                    mention_id=3,
                    place_id=2,
                    platform="ifoodie",
                    external_id="m3",
                    sentiment_score="1.00",
                    crowdedness="0.50",
                    vibe_tags=["nightlife"],
                    posted_at=utc_datetime(2026, 4, 3, 12, 0),
                ),
            ],
            features=[PlaceFeatures(place_id=1)],
        )

        with patch(
            "app.services.social_aggregation.utc_now",
            return_value=utc_datetime(2026, 4, 24, 12, 0),
        ):
            recompute_social_aggregates(session)

        self.assertEqual(place_one.mention_count, 2)
        self.assertEqual(place_one.sentiment_score, Decimal("0.70"))
        self.assertEqual(place_one.vibe_tags, ["hidden_gem", "quiet", "brunch"])
        self.assertEqual(place_one.trend_score, Decimal("1.0000"))

        self.assertEqual(place_two.mention_count, 1)
        self.assertEqual(place_two.sentiment_score, Decimal("1.00"))
        self.assertLess(place_two.trend_score, place_one.trend_score)
        self.assertEqual(place_two.vibe_tags, ["nightlife"])

        features_by_place_id = {feature.place_id: feature for feature in session.features}
        self.assertEqual(features_by_place_id[1].crowd_score, Decimal("0.5000"))
        self.assertEqual(features_by_place_id[2].crowd_score, Decimal("0.5000"))

    def test_recompute_sets_zero_mention_places_to_empty_social_summary(self):
        place = build_place(
            place_id=1,
            google_place_id="gp-zero",
            display_name="Zero Mention Place",
            district="中正區",
        )
        place.mention_count = 7
        place.vibe_tags = ["stale"]
        place.sentiment_score = Decimal("0.55")
        place.trend_score = Decimal("0.2222")
        session = FakeSession(places=[place])

        with patch(
            "app.services.social_aggregation.utc_now",
            return_value=utc_datetime(2026, 4, 24, 12, 0),
        ):
            recompute_social_aggregates(session)

        self.assertEqual(place.mention_count, 0)
        self.assertIsNone(place.vibe_tags)
        self.assertIsNone(place.sentiment_score)
        self.assertIsNone(place.trend_score)

    def test_recompute_is_idempotent_for_targeted_places(self):
        place_one = build_place(
            place_id=1,
            google_place_id="gp-1",
            display_name="Place One",
            district="中正區",
        )
        place_two = build_place(
            place_id=2,
            google_place_id="gp-2",
            display_name="Place Two",
            district="大安區",
        )
        place_two.trend_score = Decimal("0.3333")
        session = FakeSession(
            places=[place_one, place_two],
            mentions=[
                build_mention(
                    mention_id=1,
                    place_id=1,
                    platform="threads",
                    external_id="m1",
                    sentiment_score="0.80",
                    crowdedness="0.25",
                    vibe_tags=["hidden_gem"],
                    posted_at=utc_datetime(2026, 4, 23, 12, 0).astimezone(timezone.utc),
                )
            ],
        )

        with patch(
            "app.services.social_aggregation.utc_now",
            return_value=utc_datetime(2026, 4, 24, 12, 0),
        ):
            recompute_social_aggregates(session, place_ids=[1])
            first_snapshot = (
                place_one.mention_count,
                place_one.sentiment_score,
                place_one.trend_score,
                list(place_one.vibe_tags or []),
                len(session.features),
            )
            recompute_social_aggregates(session, place_ids=[1])
            second_snapshot = (
                place_one.mention_count,
                place_one.sentiment_score,
                place_one.trend_score,
                list(place_one.vibe_tags or []),
                len(session.features),
            )

        self.assertEqual(first_snapshot, second_snapshot)
        self.assertEqual(place_two.trend_score, Decimal("0.3333"))


if __name__ == "__main__":
    unittest.main()
