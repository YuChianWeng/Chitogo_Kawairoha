import unicodedata
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from app.models.place_source_google import PlaceSourceGoogle
from app.services.category import map_category

TAIPEI_DISTRICT_TYPE_PRIORITY = [
    "administrative_area_level_2",
    "sublocality",
    "sublocality_level_1",
    "administrative_area_level_3",
    "locality",
]

TAIPEI_ALLOWED_DISTRICTS = {
    "中正區",
    "大同區",
    "中山區",
    "松山區",
    "大安區",
    "萬華區",
    "信義區",
    "士林區",
    "北投區",
    "內湖區",
    "南港區",
    "文山區",
}

TAIPEI_DISTRICT_NAME_MAP = {
    "zhongzheng district": "中正區",
    "datong district": "大同區",
    "zhongshan district": "中山區",
    "songshan district": "松山區",
    "daan district": "大安區",
    "wanhua district": "萬華區",
    "xinyi district": "信義區",
    "shilin district": "士林區",
    "beitou district": "北投區",
    "neihu district": "內湖區",
    "nangang district": "南港區",
    "nankang district": "南港區",
    "wenshan district": "文山區",
}


def _safe_get(d: dict, *keys, default=None):
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def _normalize_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name).lower().strip()


def _canonicalize_district_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip().casefold()
    normalized = normalized.replace("’", "").replace("'", "")
    return " ".join(normalized.split())


def normalize_district_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).strip()
    if not normalized:
        return normalized

    if normalized in TAIPEI_ALLOWED_DISTRICTS:
        return normalized

    mapped = TAIPEI_DISTRICT_NAME_MAP.get(_canonicalize_district_key(normalized))
    if mapped:
        return mapped
    return normalized


def _extract_district(payload: dict) -> str | None:
    components = payload.get("addressComponents", [])
    for district_type in TAIPEI_DISTRICT_TYPE_PRIORITY:
        for component in components:
            types = component.get("types", [])
            if district_type in types:
                district_name = component.get("longText")
                if isinstance(district_name, str) and district_name.strip():
                    return normalize_district_name(district_name)
    return None


def ingest_google_place(
    db: Session, payload: dict, features: dict | None = None
) -> dict:
    google_place_id = payload.get("id")
    if not google_place_id:
        raise ValueError("google_place_id is required")

    raw_record = PlaceSourceGoogle(
        google_place_id=google_place_id,
        raw_json=payload,
        fetched_at=datetime.now(timezone.utc),
    )

    display_name = _safe_get(payload, "displayName", "text") or payload.get("displayName")
    if not display_name or not isinstance(display_name, str):
        db.add(raw_record)
        db.commit()
        return {
            "place_id": None,
            "google_place_id": google_place_id,
            "action": "raw_only",
        }

    district = _extract_district(payload)
    if district not in TAIPEI_ALLOWED_DISTRICTS:
        # Nearby Search can return cross-boundary results, so non-Taipei places are
        # retained only as raw payloads and never inserted into the normalized table.
        db.add(raw_record)
        db.commit()
        return {
            "place_id": None,
            "google_place_id": google_place_id,
            "action": "filtered_out",
        }

    place_data = {
        "google_place_id": google_place_id,
        "display_name": display_name,
        "normalized_name": _normalize_name(display_name),
        "primary_type": payload.get("primaryType"),
        "types_json": payload.get("types"),
        "formatted_address": payload.get("formattedAddress"),
        "district": district,
        "latitude": _safe_get(payload, "location", "latitude"),
        "longitude": _safe_get(payload, "location", "longitude"),
        "rating": payload.get("rating"),
        "user_rating_count": payload.get("userRatingCount"),
        "price_level": payload.get("priceLevel"),
        "business_status": payload.get("businessStatus"),
        "google_maps_uri": payload.get("googleMapsUri"),
        "website_uri": payload.get("websiteUri"),
        "national_phone_number": payload.get("nationalPhoneNumber"),
        "opening_hours_json": payload.get("regularOpeningHours"),
        "internal_category": map_category(payload.get("primaryType"), payload.get("types")),
        "last_synced_at": datetime.now(timezone.utc),
    }

    existing = db.query(Place).filter_by(google_place_id=google_place_id).first()
    if existing:
        place = existing
        for key, value in place_data.items():
            setattr(place, key, value)
        action = "updated"
    else:
        place = Place(**place_data)
        db.add(place)
        action = "created"

    db.flush()

    raw_record.place_id = place.id
    db.add(raw_record)

    if features is not None:
        known_feature_keys = {
            "couple_score",
            "family_score",
            "photo_score",
            "food_score",
            "culture_score",
            "rainy_day_score",
            "crowd_score",
            "transport_score",
            "hidden_gem_score",
            "feature_json",
        }
        feature_data = {k: v for k, v in features.items() if k in known_feature_keys}
        existing_features = db.query(PlaceFeatures).filter_by(place_id=place.id).first()
        if existing_features:
            for key, value in feature_data.items():
                setattr(existing_features, key, value)
        else:
            db.add(PlaceFeatures(place_id=place.id, **feature_data))

    db.commit()
    db.refresh(place)

    return {
        "place_id": place.id,
        "google_place_id": google_place_id,
        "action": action,
    }
