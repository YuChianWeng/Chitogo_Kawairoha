# Chito-Go Place Data Service

## What This Service Does

Chito-Go Place Data Service is a standalone FastAPI + PostgreSQL service for place data ingestion, normalization, storage, and retrieval.

This repository is the data service layer only. It is designed to be called by an LLM-based backend service for itinerary planning in Taipei.

Current responsibilities:

- Ingest place data from Google Places API
- Normalize place records into a consistent schema
- Store normalized records and raw source payloads
- Retrieve stored place data through structured HTTP APIs with LLM-friendly filtering, sorting, and ranking

## What This Service Does NOT Do

This service is not the full Chito-Go travel assistant product.

It does not currently implement:

- Trip planning or itinerary generation
- User accounts or authentication
- Frontend UI
- Background job processing

## Current Features

### Data layer

- PostgreSQL integration with SQLAlchemy 2.x
- FastAPI app startup with table creation on startup
- `places` table for normalized place records (includes `internal_category` column)
- `place_source_google` table for raw Google Places payloads (append-only)
- `place_features` table for optional derived scores
- `internal_category` normalization — maps 100+ Google place types to 7 internal categories: `attraction`, `food`, `shopping`, `lodging`, `transport`, `nightlife`, `other`

### Ingestion

- `POST /api/v1/places/import/google` — single-place import from Google payload
- `scripts/seed.py` — seeds a sample verified Taipei place
- `scripts/fetch_google_nearby.py` — Google Nearby Search fetch + import pipeline for all 12 Taipei districts
- `scripts/migrate_add_internal_category.py` — idempotent migration that adds the `internal_category` column and backfills existing rows
- `config/google_seed_targets.json` — all 12 Taipei district seed points and POI type groups
- Taipei district normalization (Chinese and English forms) with cross-boundary filtering

### Retrieval APIs

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/health/db` | Database connectivity check |
| GET | `/api/v1/places` | List places with basic filters |
| GET | `/api/v1/places/{place_id}` | Single place detail with optional features |
| GET | `/api/v1/places/search` | Filtered search with pagination, `open_now`, and sort |
| POST | `/api/v1/places/recommend` | Ranked recommendations with feature scoring |
| POST | `/api/v1/places/batch` | Multi-ID detail fetch, input order preserved |
| GET | `/api/v1/places/stats` | Counts by district, internal category, and primary type |
| GET | `/api/v1/places/nearby` | Coordinate-based search with `distance_m` per result |
| GET | `/api/v1/places/categories` | Static category metadata (values, labels, representative types) |

## Tech Stack

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy 2.x
- PostgreSQL 12
- `psycopg2-binary`
- `pydantic-settings`

## Project Structure

```text
.
├── app/
│   ├── core/
│   │   └── config.py
│   ├── models/
│   │   ├── place.py
│   │   ├── place_features.py
│   │   └── place_source_google.py
│   ├── routers/
│   │   ├── health.py
│   │   └── places.py
│   ├── schemas/
│   │   ├── place.py
│   │   └── retrieval.py
│   ├── services/
│   │   ├── category.py
│   │   ├── ingestion.py
│   │   ├── place_nearby.py
│   │   ├── place_recommendation.py
│   │   ├── place_retrieval.py
│   │   └── place_search.py
│   ├── db.py
│   └── main.py
├── config/
│   └── google_seed_targets.json
├── scripts/
│   ├── fetch_google_nearby.py
│   ├── import_place.py
│   ├── migrate_add_internal_category.py
│   └── seed.py
├── tests/
│   ├── direct_api_client.py
│   ├── test_batch_stats_api.py
│   ├── test_categories_api.py
│   ├── test_fetch_google_nearby.py
│   ├── test_ingestion.py
│   ├── test_nearby_api.py
│   ├── test_recommend_api.py
│   └── test_search_api.py
├── specs/
├── .env.example
├── requirements.txt
└── README.md
```

## Prerequisites

Before running locally, make sure you have:

- Python 3.11+ available
- PostgreSQL running locally
- A database named `chitogo`
- A PostgreSQL user matching the local default connection string
- `psql` installed for the verification commands in this README

Local default database connection:

```text
postgresql://chitogo_user:kawairoha@localhost:5432/chitogo
```

## Local Setup

Clone the repository, move into the project directory, and follow the steps below.

### Create and activate `.venv`

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Install dependencies

```bash
python -m pip install -r requirements.txt
```

### Configure environment variables

Create a local `.env` file from `.env.example` and set the database URL if needed.

Example:

```env
DATABASE_URL=postgresql://chitogo_user:kawairoha@localhost:5432/chitogo
```

If `.env` is missing, the app defaults to that same local PostgreSQL URL.

## Database Migration

After pulling the latest code, run the migration script to add `internal_category` to the `places` table and backfill existing rows:

```bash
python scripts/migrate_add_internal_category.py
```

The script is idempotent — re-running it is safe and has no effect if the column already exists.

## Run the App

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On startup, the app creates tables from the SQLAlchemy models using `Base.metadata.create_all(...)`.

## Verify DB Connection

```bash
curl http://localhost:8000/api/v1/health/db
```

Expected:

```json
{"status": "ok", "database": "connected"}
```

## Seed Sample Data

```bash
python scripts/seed.py
```

Running twice verifies idempotency: the normalized `places` row stays at count 1 for the same `google_place_id`, while `place_source_google` appends a new raw row each time.

Verified sample place:

- Name: `華山1914文化創意產業園區`
- District: `中正區`

## API Endpoints

### `GET /api/v1/health/db`

Database connectivity check.

### `GET /api/v1/places`

List normalized places. Query parameters: `district`, `primary_type`, `indoor`, `budget_level`, `min_rating`, `limit`, `offset`.

### `GET /api/v1/places/{place_id}`

Single place detail including optional derived features.

### `GET /api/v1/places/search`

Filtered search with pagination.

| Parameter | Type | Notes |
|---|---|---|
| `district` | string | Exact match |
| `internal_category` | string | One of 7 allowed values |
| `primary_type` | string | Exact match |
| `keyword` | string | Case-insensitive substring on `display_name` |
| `min_rating` | float | `rating >= min_rating` |
| `max_budget_level` | int | 0–4; see category.py `BUDGET_RANK` |
| `indoor` | bool | |
| `open_now` | bool | Best-effort; places without hours data are excluded |
| `sort` | string | `rating_desc` (default), `user_rating_count_desc` |
| `limit` | int | Default 20, max 100 |
| `offset` | int | Default 0 |

Response: `{"items": [...], "total": N, "limit": 20, "offset": 0}`

### `POST /api/v1/places/recommend`

Ranked place recommendations. All fields optional.

Request body:

```json
{
  "districts": ["大安區", "信義區"],
  "internal_category": "food",
  "min_rating": 4.0,
  "max_budget_level": 2,
  "indoor": true,
  "open_now": false,
  "limit": 10
}
```

When `internal_category` is omitted, defaults to `["attraction", "food", "shopping", "lodging"]` to exclude transport/parking POIs.

Ranking: mean of non-null `PlaceFeatures` scores → fallback to `rating` → fallback to `0.0`.

Response: `{"items": [...], "total": N, "limit": 10, "offset": 0}`

### `POST /api/v1/places/batch`

Fetch full detail for multiple place IDs. Unknown IDs are silently omitted. Response preserves input order.

Request body: `{"place_ids": [1, 12, 67]}`

Response: `{"items": [{full detail with features}, ...]}`

### `GET /api/v1/places/stats`

Aggregate counts across the dataset.

```json
{
  "total_places": 423,
  "by_district": {"大安區": 87, "信義區": 63},
  "by_internal_category": {"food": 198, "attraction": 112},
  "by_primary_type": {"restaurant": 145, "cafe": 53}
}
```

### `GET /api/v1/places/nearby`

Coordinate-based radius search. Uses a bounding-box SQL pre-filter followed by Python Haversine distance calculation.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `lat` | float | Yes | ±90 |
| `lng` | float | Yes | ±180 |
| `radius_m` | int | Yes | 1–10000 m |
| `internal_category` | string | No | |
| `primary_type` | string | No | |
| `min_rating` | float | No | |
| `max_budget_level` | int | No | 0–4 |
| `sort` | string | No | `distance_asc` (default), `rating_desc`, `user_rating_count_desc` |
| `limit` | int | No | Default 20, max 100 |

Each result includes a `distance_m` field. Returns 422 if `radius_m > 10000`.

### `GET /api/v1/places/categories`

Static category metadata. No database query.

```json
{
  "categories": [
    {"value": "attraction", "label": "Attraction", "representative_types": ["tourist_attraction", "museum", "park", "art_gallery"]},
    {"value": "food", "label": "Food & Drink", "representative_types": ["restaurant", "cafe", "bakery", "dessert_shop"]},
    {"value": "shopping", "label": "Shopping", "representative_types": ["shopping_mall", "market", "store"]},
    {"value": "lodging", "label": "Lodging", "representative_types": ["hotel", "hostel", "inn"]},
    {"value": "transport", "label": "Transport", "representative_types": ["subway_station", "train_station", "bus_station", "parking"]},
    {"value": "nightlife", "label": "Nightlife", "representative_types": ["bar", "pub", "night_club"]},
    {"value": "other", "label": "Other", "representative_types": []}
  ]
}
```

### `POST /api/v1/places/import/google`

Imports one Google-style place payload.

- Appends a raw record to `place_source_google`
- Creates or updates the normalized row in `places` by `google_place_id`
- Populates `internal_category` via `category.py` mapping at ingest time
- Optionally creates or updates `place_features` if `features` are provided

## Fetch and Import from Google Nearby Search

`scripts/fetch_google_nearby.py` queries the Google Places Nearby Search API for each configured Taipei district and imports results directly into the local data service.

Prerequisites: a valid Google Maps API key with Places API (New) enabled, and the data service running locally.

```bash
# Run all 12 Taipei districts
GOOGLE_MAPS_API_KEY=<your_key> python scripts/fetch_google_nearby.py

# Run a single district
GOOGLE_MAPS_API_KEY=<your_key> python scripts/fetch_google_nearby.py --district 中正區

# Include lower-priority bus station queries
GOOGLE_MAPS_API_KEY=<your_key> python scripts/fetch_google_nearby.py --include-secondary-transport
```

`config/google_seed_targets.json` defines all 12 Taipei districts with seed points, radius settings, and POI type groups.

Sample output:

```
[中正區] seed=huashan group=food_drink mode=includedTypes type=restaurant google_returned=20 imported=18 skipped_non_taipei=2 failed=0
[summary] districts=1 type_groups=6 queries=18 google_returned=200 imported=175 skipped_non_taipei=20 failed=5
```

## Running Tests

```bash
python -m unittest tests.test_ingestion tests.test_search_api tests.test_recommend_api tests.test_batch_stats_api tests.test_nearby_api tests.test_categories_api
```

The test suite uses a fake-session harness — no live database or external HTTP client required.

Coverage:

- `test_ingestion.py` — district normalization, Taipei filtering, ingestion behavior, opening hours field selection
- `test_search_api.py` — all filters, sorts, pagination, `open_now`, validation, null exclusion
- `test_recommend_api.py` — default categories, all filters, feature scoring, `open_now`, validation
- `test_batch_stats_api.py` — batch ordering, unknown IDs, features, stats aggregate counts
- `test_nearby_api.py` — radius filtering, distance sort, category/rating filters, limit, missing params
- `test_categories_api.py` — 7 categories, ordering, source-of-truth consistency
- `test_fetch_google_nearby.py` — config loading and district/type group structure

## Data Model Overview

### `places`

Normalized place records. One row per `google_place_id`.

Key fields: `display_name`, `primary_type`, `types_json`, `district`, `formatted_address`, `latitude`, `longitude`, `rating`, `user_rating_count`, `budget_level`, `indoor`, `outdoor`, `business_status`, `opening_hours_json`, `internal_category`, `trend_score`, `confidence_score`.

### `place_source_google`

Raw Google Places payloads. Append-only — multiple rows may exist for the same `google_place_id`.

### `place_features`

Optional derived scores per place. One row per `place_id`.

Score columns: `couple_score`, `family_score`, `food_score`, `culture_score`, `rainy_day_score`, `crowd_score`, `transport_score`, `hidden_gem_score`, `photo_score`.

### `internal_category` mapping

Defined in `app/services/category.py`. Maps 100+ Google place types to 7 values. Priority: `primary_type` → first match in `types_json` → `"other"`. Budget rank: `PRICE_LEVEL_FREE=0`, `INEXPENSIVE=1`, `MODERATE=2`, `EXPENSIVE=3`, `VERY_EXPENSIVE=4`.

## Known Limitations

- No Alembic or migration workflow (migration runs via standalone script)
- No authentication or authorization
- No delete or archive endpoints for places
- No background ingestion jobs or queue processing
- No raw payload retention policy or pruning
- `open_now` filter is best-effort: places without `regularOpeningHours.periods` data are excluded when `open_now=true`
