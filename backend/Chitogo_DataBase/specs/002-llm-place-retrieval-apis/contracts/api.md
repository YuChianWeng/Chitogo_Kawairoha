# API Contracts: LLM-friendly Place Retrieval APIs

**Feature**: `002-llm-place-retrieval-apis`
**Date**: 2026-04-18
**Base prefix**: `/api/v1`

---

## Shared Response Envelope

All list endpoints return:

```json
{
  "items": [...],
  "total": 142,
  "limit": 20,
  "offset": 0
}
```

All error responses return:

```json
{
  "detail": "human-readable error message"
}
```

---

## Shared Place Schema (PlaceCandidateOut)

Returned by search, nearby, recommend:

```json
{
  "id": 1,
  "google_place_id": "ChIJ...",
  "display_name": "華山1914文化創意產業園區",
  "internal_category": "attraction",
  "primary_type": "tourist_attraction",
  "district": "中正區",
  "formatted_address": "10491台北市中正區八德路一段1號",
  "latitude": 25.0441,
  "longitude": 121.5292,
  "rating": 4.4,
  "user_rating_count": 12000,
  "budget_level": "MODERATE",
  "indoor": null,
  "outdoor": null,
  "business_status": "OPERATIONAL",
  "google_maps_uri": "https://maps.google.com/?cid=..."
}
```

---

## GET /api/v1/places/search

**User story**: US-1, US-4

### Query parameters

| Param | Type | Required | Notes |
|---|---|---|---|
| `district` | string | No | Exact match |
| `internal_category` | string | No | One of allowed values |
| `primary_type` | string | No | Exact match |
| `keyword` | string | No | ilike on `display_name` |
| `min_rating` | float | No | `rating >= min_rating` |
| `max_budget_level` | int | No | 0–4; see data-model.md |
| `indoor` | bool | No | |
| `open_now` | bool | No | Best-effort; see data-model.md |
| `sort` | string | No | `rating_desc` (default), `user_rating_count_desc` |
| `limit` | int | No | Default 20, max 100 |
| `offset` | int | No | Default 0 |

### Response 200

```json
{
  "items": [PlaceCandidateOut, ...],
  "total": 58,
  "limit": 20,
  "offset": 0
}
```

### Errors

- `422` — invalid `sort` value, `limit` > 100, `max_budget_level` outside 0–4, invalid `internal_category`

---

## GET /api/v1/places/nearby

**User story**: US-2

### Query parameters

| Param | Type | Required | Notes |
|---|---|---|---|
| `lat` | float | **Yes** | ±90 |
| `lng` | float | **Yes** | ±180 |
| `radius_m` | int | **Yes** | 1–10000 |
| `internal_category` | string | No | |
| `primary_type` | string | No | |
| `min_rating` | float | No | |
| `max_budget_level` | int | No | |
| `sort` | string | No | `distance_asc` (default), `rating_desc`, `user_rating_count_desc` |
| `limit` | int | No | Default 20, max 100 |

### Response 200

Each item extends `PlaceCandidateOut` with:

```json
{
  "id": 1,
  "display_name": "...",
  "internal_category": "attraction",
  "distance_m": 342.7,
  ...
}
```

### Errors

- `422` — missing required params, `radius_m` > 10000, coordinates out of range, invalid `sort`

---

## POST /api/v1/places/batch

**User story**: US-3

### Request body

```json
{
  "place_ids": [1, 12, 67, 141]
}
```

### Response 200

Returns `PlaceDetailOut` (all normalized fields + features block) for each known ID.
Unknown IDs are silently omitted. Order matches `place_ids` order.

```json
{
  "items": [
    {
      "id": 1,
      "google_place_id": "ChIJ...",
      "display_name": "...",
      "internal_category": "attraction",
      "primary_type": "tourist_attraction",
      "types_json": ["tourist_attraction", "point_of_interest"],
      "district": "中正區",
      "formatted_address": "...",
      "latitude": 25.0441,
      "longitude": 121.5292,
      "rating": 4.4,
      "user_rating_count": 12000,
      "price_level": null,
      "budget_level": "MODERATE",
      "business_status": "OPERATIONAL",
      "indoor": null,
      "outdoor": null,
      "trend_score": null,
      "confidence_score": null,
      "google_maps_uri": "...",
      "website_uri": null,
      "national_phone_number": null,
      "opening_hours_json": null,
      "created_at": "2026-04-18T10:00:00Z",
      "updated_at": "2026-04-18T10:00:00Z",
      "features": {
        "couple_score": 0.82,
        "family_score": null,
        "food_score": null,
        "culture_score": 0.91,
        "rainy_day_score": null,
        "crowd_score": 0.55,
        "transport_score": 0.78,
        "hidden_gem_score": null,
        "feature_json": null,
        "updated_at": "2026-04-18T10:00:00Z"
      }
    }
  ]
}
```

`features` is `null` if no `PlaceFeatures` row exists.

### Errors

- `422` — `place_ids` is empty or not a list, `place_ids` contains non-integer values
- `200` with `{"items": []}` — all IDs unknown (not 404)

---

## POST /api/v1/places/recommend

**User story**: US-5

### Request body

```json
{
  "districts": ["大安區", "信義區"],
  "internal_category": "food",
  "min_rating": 4.2,
  "max_budget_level": 2,
  "indoor": true,
  "open_now": false,
  "limit": 10
}
```

All fields optional. `limit` default 10, max 50.

### Default category behavior

If `internal_category` is **not provided**, the endpoint defaults to filtering `internal_category IN ("attraction", "food", "shopping", "lodging")`. This prevents transport/parking POIs from dominating results. Pass `internal_category` explicitly to override.

### Ranking

1. If `PlaceFeatures` exist: sort by mean of non-null feature scores (DESC), then `rating DESC`.
2. If no features: sort by `rating DESC`.

### Response 200

```json
{
  "items": [PlaceCandidateOut, ...],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

### Errors

- `422` — `limit` > 50, invalid `internal_category`, `max_budget_level` outside 0–4

---

## GET /api/v1/places/stats

**User story**: US-6

### Response 200

```json
{
  "total_places": 423,
  "by_district": {
    "大安區": 87,
    "信義區": 63,
    "中正區": 55
  },
  "by_internal_category": {
    "food": 198,
    "attraction": 112,
    "shopping": 67,
    "transport": 21,
    "lodging": 15,
    "nightlife": 8,
    "other": 2
  },
  "by_primary_type": {
    "restaurant": 145,
    "tourist_attraction": 89,
    "cafe": 53
  }
}
```

---

## GET /api/v1/places/categories

**User story**: US-4

### Response 200

```json
{
  "categories": [
    {
      "value": "attraction",
      "label": "Attraction",
      "representative_types": ["tourist_attraction", "museum", "park", "art_gallery"]
    },
    {
      "value": "food",
      "label": "Food & Drink",
      "representative_types": ["restaurant", "cafe", "bakery", "dessert_shop"]
    },
    {
      "value": "shopping",
      "label": "Shopping",
      "representative_types": ["shopping_mall", "market", "store"]
    },
    {
      "value": "lodging",
      "label": "Lodging",
      "representative_types": ["hotel", "hostel", "inn"]
    },
    {
      "value": "transport",
      "label": "Transport",
      "representative_types": ["subway_station", "train_station", "bus_station", "parking"]
    },
    {
      "value": "nightlife",
      "label": "Nightlife",
      "representative_types": ["bar", "pub", "night_club"]
    },
    {
      "value": "other",
      "label": "Other",
      "representative_types": []
    }
  ]
}
```

---

## Backward-compatible endpoints (unchanged)

| Endpoint | Change |
|---|---|
| `GET /api/v1/places` | None — existing behavior preserved |
| `GET /api/v1/places/{place_id}` | None — existing behavior preserved |
| `POST /api/v1/places/import/google` | `internal_category` now populated at ingest time |
| `GET /api/v1/health/db` | None |
