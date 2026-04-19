from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.models  # noqa: F401
from app.db import Base, SessionLocal, engine
from app.models.place import Place
from app.models.place_source_google import PlaceSourceGoogle
from app.services.ingestion import ingest_google_place


SAMPLE_GOOGLE_PLACE_ID = "ChIJH8B5JxapQjQR3KX8A2Q9V4o"
SAMPLE_GOOGLE_PAYLOAD = {
    "id": SAMPLE_GOOGLE_PLACE_ID,
    "displayName": {"text": "華山1914文化創意產業園區"},
    "primaryType": "tourist_attraction",
    "types": [
        "tourist_attraction",
        "cultural_landmark",
        "event_venue",
        "point_of_interest",
        "establishment",
    ],
    "formattedAddress": "10058台灣台北市中正區八德路一段1號",
    "addressComponents": [
        {
            "longText": "10058",
            "shortText": "10058",
            "types": ["postal_code"],
            "languageCode": "zh-TW",
        },
        {
            "longText": "台灣",
            "shortText": "TW",
            "types": ["country", "political"],
            "languageCode": "zh-TW",
        },
        {
            "longText": "台北市",
            "shortText": "台北市",
            "types": ["administrative_area_level_1", "political"],
            "languageCode": "zh-TW",
        },
        {
            "longText": "中正區",
            "shortText": "中正區",
            "types": ["sublocality", "political"],
            "languageCode": "zh-TW",
        },
        {
            "longText": "八德路一段1號",
            "shortText": "1號",
            "types": ["route"],
            "languageCode": "zh-TW",
        },
    ],
    "location": {"latitude": 25.0440581, "longitude": 121.5298485},
    "rating": 4.4,
    "userRatingCount": 12000,
    "businessStatus": "OPERATIONAL",
    "googleMapsUri": "https://maps.google.com/?cid=4342178518828401116",
    "websiteUri": "https://www.huashan1914.com/",
    "nationalPhoneNumber": "+886 2 2358 1914",
    "regularOpeningHours": {
        "openNow": True,
        "weekdayDescriptions": [
            "星期一: 09:30 – 21:00",
            "星期二: 09:30 – 21:00",
            "星期三: 09:30 – 21:00",
            "星期四: 09:30 – 21:00",
            "星期五: 09:30 – 21:00",
            "星期六: 09:30 – 21:00",
            "星期日: 09:30 – 21:00",
        ],
        "periods": [
            {
                "open": {"day": 0, "hour": 9, "minute": 30},
                "close": {"day": 0, "hour": 21, "minute": 0},
            }
        ],
    },
}


def main() -> int:
    print("[seed] Connecting to database...")
    Base.metadata.create_all(bind=engine)
    print("[seed] Tables verified.")

    db = SessionLocal()
    try:
        before_raw_count = (
            db.query(PlaceSourceGoogle)
            .filter(PlaceSourceGoogle.google_place_id == SAMPLE_GOOGLE_PLACE_ID)
            .count()
        )
        result = ingest_google_place(db, SAMPLE_GOOGLE_PAYLOAD)

        place = (
            db.query(Place)
            .filter(Place.google_place_id == SAMPLE_GOOGLE_PLACE_ID)
            .first()
        )
        after_raw_count = (
            db.query(PlaceSourceGoogle)
            .filter(PlaceSourceGoogle.google_place_id == SAMPLE_GOOGLE_PLACE_ID)
            .count()
        )
        place_count = (
            db.query(Place)
            .filter(Place.google_place_id == SAMPLE_GOOGLE_PLACE_ID)
            .count()
        )

        if result["action"] == "created":
            print(
                f"[seed] Inserted place: {SAMPLE_GOOGLE_PAYLOAD['displayName']['text']} "
                f"(id={result['place_id']})"
            )
        else:
            print(
                f"[seed] Place already exists: {SAMPLE_GOOGLE_PAYLOAD['displayName']['text']} "
                f"(id={result['place_id']})"
            )

        if after_raw_count == before_raw_count + 1:
            print(
                "[seed] Appended raw source row for "
                f"google_place_id={SAMPLE_GOOGLE_PLACE_ID} "
                f"(total_raw_rows={after_raw_count})"
            )
        else:
            print(
                "[seed] Raw source row count changed unexpectedly for "
                f"google_place_id={SAMPLE_GOOGLE_PLACE_ID}: "
                f"before={before_raw_count}, after={after_raw_count}"
            )

        if place is not None:
            print(
                "[seed] Normalized place verification: "
                f"name={place.display_name}, district={place.district}, "
                f"place_rows={place_count}"
            )

        print("[seed] Done.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
