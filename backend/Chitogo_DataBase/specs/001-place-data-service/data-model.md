# Data Model: Place Data Service

**Feature**: 001-place-data-service
**Date**: 2026-04-16
**Phase**: 1 — Design

---

## Entity Overview

```
places (1) ──< place_source_google (many)
places (1) ──| place_features (0 or 1)
```

- `places` is the root entity. All other tables reference it via `place_id`.
- `place_source_google` is append-only. One row per ingestion call.
- `place_features` is optional and one-to-one. Created only when score data is provided.

---

## Table: places

**Purpose**: Normalized internal representation of a location. Source-agnostic. Contains all fields needed for display or filtering by downstream backends.

**ORM file**: `app/models/place.py`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK, autoincrement | Internal surrogate key |
| google_place_id | String(255) | UNIQUE, NOT NULL, indexed | Deduplication key; required for ingest |
| display_name | String(512) | NOT NULL | Required for normalized record creation |
| normalized_name | String(512) | nullable | Lowercase + stripped + NFKC of display_name |
| primary_type | String(128) | nullable | e.g. "restaurant", "tourist_attraction" |
| types_json | JSONB | nullable | Full types array from source |
| formatted_address | String(1024) | nullable | Human-readable address |
| district | String(255) | nullable, indexed | Extracted from address components |
| latitude | Numeric(10,7) | nullable | |
| longitude | Numeric(10,7) | nullable | |
| rating | Numeric(3,1) | nullable | 0.0–5.0 |
| user_rating_count | Integer | nullable | |
| price_level | String(64) | nullable | Raw value from source (e.g. "PRICE_LEVEL_MODERATE") |
| business_status | String(64) | nullable | e.g. "OPERATIONAL", "CLOSED_TEMPORARILY" |
| google_maps_uri | String(1024) | nullable | |
| website_uri | String(1024) | nullable | |
| national_phone_number | String(32) | nullable | |
| opening_hours_json | JSONB | nullable | Structured hours from source |
| indoor | Boolean | nullable | Derived; null until enriched |
| outdoor | Boolean | nullable | Derived; null until enriched |
| budget_level | String(32) | nullable, indexed | e.g. "budget", "mid-range", "upscale"; derived |
| trend_score | Numeric(5,4) | nullable | Service-level score; derived |
| confidence_score | Numeric(5,4) | nullable | Service-level score; derived |
| created_at | DateTime(tz=True) | NOT NULL, server_default=now() | |
| updated_at | DateTime(tz=True) | NOT NULL, onupdate=now() | |
| last_synced_at | DateTime(tz=True) | nullable | Set at ingest time |

**Indexes**:
- PRIMARY KEY on `id`
- UNIQUE on `google_place_id`
- Index on `district` (filter support)
- Index on `primary_type` (filter support)
- Index on `budget_level` (filter support)

**Validation rules** (from spec FR-007):
- `google_place_id` must be present; reject entire payload if missing.
- `display_name` must be present; store raw payload but skip place record creation if missing.

---

## Table: place_source_google

**Purpose**: Append-only retention of raw Google Places API payloads. One row per ingestion call. Never updated or deleted in this milestone.

**ORM file**: `app/models/place_source_google.py`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK, autoincrement | |
| place_id | Integer | FK → places.id, NOT NULL, indexed | Owning place |
| google_place_id | String(255) | NOT NULL | Denormalized for direct lookup without join |
| raw_json | JSONB | NOT NULL | Full unmodified source payload |
| fetched_at | DateTime(tz=True) | NOT NULL, default=now() | Time payload was received by this service |

**Indexes**:
- PRIMARY KEY on `id`
- Index on `place_id`
- Index on `google_place_id`

**Retention note**: Append-only in this milestone. Retention policy (keep last N per `google_place_id`) is deferred.

---

## Table: place_features

**Purpose**: Extended audience and context ranking scores, consumed by downstream recommendation systems. Not used for direct filtering or display. One-to-one with `places`; optional (created only when score data is provided at ingest or via a separate write).

**ORM file**: `app/models/place_features.py`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| place_id | Integer | PK, FK → places.id | One-to-one; also the PK |
| couple_score | Numeric(5,4) | nullable | 0.0–1.0 |
| family_score | Numeric(5,4) | nullable | 0.0–1.0 |
| photo_score | Numeric(5,4) | nullable | 0.0–1.0 |
| food_score | Numeric(5,4) | nullable | 0.0–1.0 |
| culture_score | Numeric(5,4) | nullable | 0.0–1.0 |
| rainy_day_score | Numeric(5,4) | nullable | 0.0–1.0 |
| crowd_score | Numeric(5,4) | nullable | 0.0–1.0 |
| transport_score | Numeric(5,4) | nullable | 0.0–1.0 |
| hidden_gem_score | Numeric(5,4) | nullable | 0.0–1.0 |
| feature_json | JSONB | nullable | Open-ended extended feature dictionary |
| updated_at | DateTime(tz=True) | NOT NULL, onupdate=now() | |

**Indexes**:
- PRIMARY KEY on `place_id`

---

## Relationship Summary

```python
# places → place_source_google (one-to-many)
class Place(Base):
    source_records = relationship("PlaceSourceGoogle", back_populates="place")

class PlaceSourceGoogle(Base):
    place = relationship("Place", back_populates="source_records")

# places → place_features (one-to-one)
class Place(Base):
    features = relationship("PlaceFeatures", uselist=False, back_populates="place")

class PlaceFeatures(Base):
    place = relationship("Place", back_populates="features")
```

---

## Field Categorization

### Filterable fields (query params on GET /api/v1/places)
- `district` — String equality
- `primary_type` — String equality
- `indoor` — Boolean
- `budget_level` — String equality
- `rating` — Numeric ≥ (min_rating)

### Display-only fields (returned in detail response, not filterable)
- `normalized_name`, `types_json`, `formatted_address`, `latitude`, `longitude`
- `user_rating_count`, `price_level`, `business_status`
- `google_maps_uri`, `website_uri`, `national_phone_number`, `opening_hours_json`
- `outdoor`, `trend_score`, `confidence_score`
- `created_at`, `updated_at`, `last_synced_at`

### Downstream-only fields (place_features, not returned in place list/detail)
- All score fields; available via join if downstream consumers need them

---

## Pydantic Response Schemas

### PlaceListItem (GET /api/v1/places list response)
Minimal set: `id`, `google_place_id`, `display_name`, `primary_type`, `district`, `formatted_address`, `rating`, `indoor`, `outdoor`, `budget_level`, `trend_score`

### PlaceDetail (GET /api/v1/places/{place_id} detail response)
Full set: all Place fields. Features block included if record exists.

### GoogleImportPayload (POST /api/v1/places/import/google request body)
```json
{
  "payload": { ...raw Google Places object... },
  "features": {
    "couple_score": 0.85,
    "food_score": 0.70
  }
}
```
Both `payload` and `features` accepted as raw dicts. `features` is optional.

### ImportResult (POST response)
```json
{
  "place_id": 1,
  "google_place_id": "ChIJ...",
  "action": "created"
}
```
