# API Contract: Place Data Service

**Version**: v1
**Base path**: `/api/v1`
**Format**: JSON (application/json)
**Auth**: None (trusted network; no authentication for this milestone)

---

## GET /api/v1/health/db

Confirms service is running and the database connection is reachable.

**Request**: No parameters.

**Response 200 — healthy**:
```json
{
  "status": "ok",
  "database": "connected"
}
```

**Response 503 — database unreachable**:
```json
{
  "status": "error",
  "database": "unreachable",
  "detail": "could not connect to server"
}
```

---

## GET /api/v1/places

Returns a list of normalized place records. All filters are optional. Returns an empty list (not an error) when no records match.

**Query parameters**:

| Parameter | Type | Description |
|---|---|---|
| district | string | Filter by district (exact match) |
| primary_type | string | Filter by primary_type (exact match) |
| indoor | boolean | Filter by indoor flag (true/false) |
| budget_level | string | Filter by budget_level (e.g. "budget", "mid-range", "upscale") |
| min_rating | float | Minimum rating (inclusive, e.g. 4.0) |
| limit | int | Max records to return (default: 50, max: 200) |
| offset | int | Pagination offset (default: 0) |

**Response 200**:
```json
[
  {
    "id": 1,
    "google_place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
    "display_name": "Shibuya Crossing",
    "primary_type": "tourist_attraction",
    "district": "Shibuya",
    "formatted_address": "2-chome Dogenzaka, Shibuya City, Tokyo",
    "rating": 4.6,
    "indoor": false,
    "outdoor": true,
    "budget_level": "budget",
    "trend_score": null
  }
]
```

---

## GET /api/v1/places/{place_id}

Returns the full normalized detail for a single place, including features if available.

**Path parameters**:

| Parameter | Type | Description |
|---|---|---|
| place_id | integer | Internal place ID |

**Response 200**:
```json
{
  "id": 1,
  "google_place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
  "display_name": "Shibuya Crossing",
  "normalized_name": "shibuya crossing",
  "primary_type": "tourist_attraction",
  "types_json": ["tourist_attraction", "point_of_interest"],
  "formatted_address": "2-chome Dogenzaka, Shibuya City, Tokyo",
  "district": "Shibuya",
  "latitude": 35.6595,
  "longitude": 139.7004,
  "rating": 4.6,
  "user_rating_count": 82341,
  "price_level": "PRICE_LEVEL_FREE",
  "business_status": "OPERATIONAL",
  "google_maps_uri": "https://maps.google.com/?cid=...",
  "website_uri": null,
  "national_phone_number": null,
  "opening_hours_json": null,
  "indoor": false,
  "outdoor": true,
  "budget_level": "budget",
  "trend_score": null,
  "confidence_score": null,
  "created_at": "2026-04-16T10:00:00Z",
  "updated_at": "2026-04-16T10:00:00Z",
  "last_synced_at": "2026-04-16T10:00:00Z",
  "features": null
}
```

**Response 404**:
```json
{
  "detail": "Place not found"
}
```

**features block (when present)**:
```json
"features": {
  "couple_score": 0.85,
  "family_score": 0.60,
  "photo_score": 0.92,
  "food_score": 0.10,
  "culture_score": 0.88,
  "rainy_day_score": 0.30,
  "crowd_score": 0.95,
  "transport_score": 0.99,
  "hidden_gem_score": 0.05,
  "feature_json": {},
  "updated_at": "2026-04-16T10:00:00Z"
}
```

---

## POST /api/v1/places/import/google

Accepts a raw Google Places (New) API JSON payload and ingests it into the internal place schema. Upserts by `google_place_id`. Also accepts an optional `features` block.

**Request body**:
```json
{
  "payload": {
    "id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
    "displayName": { "text": "Shibuya Crossing", "languageCode": "en" },
    "primaryType": "tourist_attraction",
    "types": ["tourist_attraction", "point_of_interest"],
    "formattedAddress": "2-chome Dogenzaka, Shibuya City, Tokyo",
    "location": { "latitude": 35.6595, "longitude": 139.7004 },
    "rating": 4.6,
    "userRatingCount": 82341,
    "businessStatus": "OPERATIONAL",
    "googleMapsUri": "https://maps.google.com/?cid=..."
  },
  "features": {
    "couple_score": 0.85,
    "photo_score": 0.92
  }
}
```

`payload` is required. `features` is optional — if omitted, the place_features row is left untouched.

**Response 200 — created**:
```json
{
  "place_id": 1,
  "google_place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
  "action": "created"
}
```

**Response 200 — updated**:
```json
{
  "place_id": 1,
  "google_place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
  "action": "updated"
}
```

**Response 422 — missing google_place_id**:
```json
{
  "detail": "google_place_id is required"
}
```

**Response 422 — missing display_name (raw payload still stored)**:
```json
{
  "detail": "display_name is required for normalized record; raw payload stored only",
  "google_place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
  "action": "raw_only"
}
```

---

## Error conventions

| Status | Meaning |
|---|---|
| 200 | Success |
| 404 | Record not found |
| 422 | Validation error (missing required field, bad type) |
| 503 | Database unreachable (health endpoint only) |

All error responses include a `"detail"` string field.
