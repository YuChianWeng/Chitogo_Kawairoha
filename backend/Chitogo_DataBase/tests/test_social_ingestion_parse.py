import unittest
from datetime import timedelta
from decimal import Decimal

from app.services.social_ingestion import parse_crawl_row


class SocialIngestionParseTests(unittest.TestCase):
    def test_parse_handles_json_array_tags_and_taipei_spots_place_id(self):
        mention = parse_crawl_row(
            {
                "id": "200",
                "platform": "Threads",
                "location": "JSON Tag Place",
                "sentiment_score": "0.95",
                "crowdedness": "0.50",
                "vibe_tags": '["Hidden Gem", "Late-night"]',
                "original_text": "hello",
                "source_url": "https://example.com/post",
                "created_at": "2026-04-20 20:00:00",
                "address": "104臺北市中山區南京東路一段1號",
                "place_id": "gp-json",
            },
            source_hint="taipei_spots",
        )

        self.assertEqual(mention.google_place_id, "gp-json")
        self.assertEqual(mention.platform, "threads")
        self.assertEqual(mention.vibe_tags, ["hidden_gem", "late_night"])
        self.assertEqual(mention.sentiment_score, Decimal("0.95"))
        self.assertEqual(mention.crowdedness, Decimal("0.50"))
        self.assertEqual(mention.posted_at.utcoffset(), timedelta(hours=8))

    def test_parse_handles_comma_separated_tags(self):
        mention = parse_crawl_row(
            {
                "id": "101",
                "platform": "ifoodie",
                "location": "Comma Tag Place",
                "address": "100臺北市中正區北平西路3號",
                "google_place_id": "gp-comma",
                "sentiment_score": "0.80",
                "crowdedness": "0.20",
                "vibe_tags": "Thai food, restaurant, trendy",
                "original_text": "hello",
                "source_url": "",
                "created_at": "2026-04-21 11:30:00",
            }
        )

        self.assertEqual(mention.platform, "ifoodie")
        self.assertEqual(mention.vibe_tags, ["thai_food", "restaurant", "trendy"])
        self.assertIsNone(mention.source_url)

    def test_parse_deduplicates_duplicate_tags_within_one_row(self):
        mention = parse_crawl_row(
            {
                "id": "102",
                "platform": "Threads",
                "location": "Duplicate Tags Place",
                "address": "100臺北市中正區北平西路3號",
                "place_id": "gp-duplicate-tags",
                "sentiment_score": "0.80",
                "crowdedness": "0.20",
                "vibe_tags": '["Hidden Gem", "hidden gem", "Late-night", "late night"]',
                "original_text": "hello",
                "source_url": "",
                "created_at": "2026-04-21 11:30:00",
            }
        )

        self.assertEqual(mention.vibe_tags, ["hidden_gem", "late_night"])

    def test_parse_uses_source_hint_when_platform_is_missing(self):
        mention = parse_crawl_row(
            {
                "id": "5",
                "platform": "",
                "location": "Hinted Platform Place",
                "address": "106臺北市大安區杭州南路二段61巷39號",
                "google_place_id": "gp-source-hint",
                "sentiment_score": "",
                "crowdedness": "",
                "vibe_tags": "",
                "original_text": "",
                "source_url": "",
                "created_at": "",
            },
            source_hint="ifoodie",
        )

        self.assertEqual(mention.platform, "ifoodie")
        self.assertIsNone(mention.posted_at)
        self.assertEqual(mention.vibe_tags, [])

    def test_parse_rejects_missing_google_place_id(self):
        with self.assertRaisesRegex(ValueError, "google_place_id is required"):
            parse_crawl_row(
                {
                    "id": "7",
                    "platform": "ifoodie",
                    "location": "Missing ID Place",
                    "address": "100臺北市中正區北平西路3號",
                    "google_place_id": "",
                    "sentiment_score": "0.40",
                    "crowdedness": "0.10",
                    "vibe_tags": "test",
                    "original_text": "hello",
                    "source_url": "",
                    "created_at": "2026-04-24 09:00:00",
                }
            )


if __name__ == "__main__":
    unittest.main()
