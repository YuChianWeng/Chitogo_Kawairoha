import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from app.services import social_ingestion
from app.services.social_ingestion import import_crawl_csv
from tests.social_test_support import FakeSession, build_google_payload, build_place


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "social"


class StubGoogleClient:
    def __init__(self, payloads: dict[str, dict]):
        self.payloads = payloads
        self.calls: list[str] = []

    def fetch_place(self, google_place_id: str) -> dict | None:
        self.calls.append(google_place_id)
        return self.payloads.get(google_place_id)


class ImportCrawlCsvTests(unittest.TestCase):
    def test_import_ifoodie_fixture_and_rerun_is_idempotent_for_mentions(self):
        session = FakeSession(
            places=[
                build_place(
                    place_id=1,
                    google_place_id="gp-db-hit-ifoodie",
                    display_name="Existing Cafe",
                    district="大安區",
                    internal_category="food",
                )
            ]
        )
        google_client = StubGoogleClient(
            {
                "gp-google-ifoodie": build_google_payload(
                    google_place_id="gp-google-ifoodie",
                    display_name="Google Bistro",
                    district="中正區",
                    primary_type="restaurant",
                )
            }
        )

        stats = import_crawl_csv(
            session,
            FIXTURES_DIR / "ifoodie_sample.csv",
            source_hint="ifoodie",
            google_client=google_client,
        )

        self.assertEqual(
            stats.as_dict(),
            {
                "db_hit": 1,
                "google_enriched": 1,
                "fallback_inserted": 1,
                "filtered_out": 1,
                "duplicate_mention": 1,
                "error": 0,
            },
        )
        self.assertEqual(len(session.places), 3)
        self.assertEqual(len(session.mentions), 3)
        self.assertEqual(len(session.raw_records), 2)
        self.assertEqual(
            {place.google_place_id: place.mention_count for place in session.places},
            {
                "gp-db-hit-ifoodie": 1,
                "gp-google-ifoodie": 1,
                "gp-fallback-ifoodie": 1,
            },
        )
        fallback_place = next(
            place for place in session.places if place.google_place_id == "gp-fallback-ifoodie"
        )
        self.assertEqual(fallback_place.district, "信義區")
        mentions_by_external_id = {
            mention.external_id: mention for mention in session.mentions
        }
        self.assertEqual(mentions_by_external_id["100"].vibe_tags, ["coffee", "cozy"])
        self.assertEqual(
            mentions_by_external_id["101"].vibe_tags, ["trendy", "brunch"]
        )
        self.assertEqual(
            mentions_by_external_id["102"].vibe_tags, ["hidden_gem", "noodles"]
        )
        self.assertEqual(google_client.calls, ["gp-google-ifoodie", "gp-fallback-ifoodie", "gp-filter-ifoodie"])

        rerun_stats = import_crawl_csv(
            session,
            FIXTURES_DIR / "ifoodie_sample.csv",
            source_hint="ifoodie",
            google_client=google_client,
        )

        self.assertEqual(
            rerun_stats.as_dict(),
            {
                "db_hit": 0,
                "google_enriched": 0,
                "fallback_inserted": 0,
                "filtered_out": 1,
                "duplicate_mention": 4,
                "error": 0,
            },
        )
        self.assertEqual(len(session.places), 3)
        self.assertEqual(len(session.mentions), 3)
        self.assertEqual(len(session.raw_records), 2)

    def test_import_taipei_spots_fixture_without_enrichment(self):
        session = FakeSession(
            places=[
                build_place(
                    place_id=1,
                    google_place_id="gp-db-hit-threads",
                    display_name="Existing Threads Cafe",
                    district="中山區",
                    internal_category="food",
                )
            ]
        )

        stats = import_crawl_csv(
            session,
            FIXTURES_DIR / "taipei_spots_sample.csv",
            source_hint="taipei_spots",
            google_client=None,
        )

        self.assertEqual(
            stats.as_dict(),
            {
                "db_hit": 1,
                "google_enriched": 0,
                "fallback_inserted": 2,
                "filtered_out": 1,
                "duplicate_mention": 1,
                "error": 0,
            },
        )
        self.assertEqual(len(session.places), 3)
        self.assertEqual(len(session.mentions), 3)
        self.assertEqual(len(session.raw_records), 1)
        mentions_by_external_id = {
            mention.external_id: mention for mention in session.mentions
        }
        self.assertEqual(
            mentions_by_external_id["200"].vibe_tags, ["hidden_gem", "late_night"]
        )
        self.assertEqual(mentions_by_external_id["201"].platform, "instagram")
        self.assertEqual(
            mentions_by_external_id["202"].vibe_tags, ["artsy", "quiet_corner"]
        )

    def test_import_continues_after_unexpected_row_error(self):
        session = FakeSession(
            places=[
                build_place(
                    place_id=1,
                    google_place_id="gp-db-hit-ifoodie",
                    display_name="Existing Cafe",
                    district="大安區",
                    internal_category="food",
                ),
                build_place(
                    place_id=2,
                    google_place_id="gp-next-row",
                    display_name="Next Row Cafe",
                    district="中正區",
                    internal_category="food",
                ),
            ]
        )
        csv_text = (
            "id,platform,location,address,google_place_id,sentiment_score,crowdedness,"
            "vibe_tags,original_text,source_url,created_at\n"
            "900,ifoodie,Broken Row,106臺北市大安區仁愛路四段100號,gp-db-hit-ifoodie,"
            "0.80,0.30,\"coffee, cozy\",Broken row,,2026-04-20 10:00:00\n"
            "901,ifoodie,Next Row,100臺北市中正區北平西路3號,gp-next-row,"
            "0.70,0.20,\"tea, calm\",Next row,,2026-04-21 10:00:00\n"
        )

        original_resolve_place = social_ingestion._resolve_place

        def flaky_resolve_place(db, mention, *, google_client):
            if mention.external_id == "900":
                raise RuntimeError("boom")
            return original_resolve_place(db, mention, google_client=google_client)

        with NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv") as temp_file:
            temp_file.write(csv_text)
            temp_file.flush()

            with self.assertLogs("app.services.social_ingestion", level="ERROR") as logs:
                with patch(
                    "app.services.social_ingestion._resolve_place",
                    side_effect=flaky_resolve_place,
                ):
                    stats = import_crawl_csv(
                        session,
                        Path(temp_file.name),
                        source_hint="ifoodie",
                        google_client=None,
                    )

        self.assertEqual(
            stats.as_dict(),
            {
                "db_hit": 1,
                "google_enriched": 0,
                "fallback_inserted": 0,
                "filtered_out": 0,
                "duplicate_mention": 0,
                "error": 1,
            },
        )
        self.assertEqual(len(session.mentions), 1)
        self.assertEqual(session.mentions[0].external_id, "901")
        self.assertEqual(session.rollback_count, 1)
        self.assertIn("error processing row 900", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
