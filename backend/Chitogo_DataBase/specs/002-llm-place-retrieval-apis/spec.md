# Feature Specification: LLM-friendly Place Retrieval APIs

**Feature Branch**: `feature/llm-place-retrieval-apis`
**Created**: 2026-04-18
**Status**: Clarified
**Depends on**: `001-place-data-service` (existing normalized places table)

---

## Summary

Add LLM-friendly retrieval APIs on top of the existing Taipei POI database so the main backend can efficiently search, filter, batch-fetch, and recommend places without directly reasoning over raw database rows.

---

## Non-Goals

- Itinerary generation
- Route optimization / map routing
- Session memory orchestration
- Chat workflow logic
- External review crawling
- Ranking model training

---

## Clarifications

### Schema decisions

- **internal_category is stored in DB**, not derived at runtime. Stored in a new indexed column on `places`. Mapped at ingest time. A one-off backfill script handles existing rows. Reasoning: stored column allows efficient SQL filtering and indexing.
- **budget_level numeric ordering**: The existing `budget_level` field stores Google's string values. For `max_budget_level` filtering, a deterministic numeric rank is defined: `INEXPENSIVE=1`, `MODERATE=2`, `EXPENSIVE=3`, `VERY_EXPENSIVE=4`. The filter operates on this rank mapping in the query layer.
- **open_now is best-effort**: Only evaluated when `opening_hours_json` contains a `periods` array. Places without this data are excluded from results when `open_now=true`, not silently included.
- **keyword search**: Uses `ilike` on `display_name`. No full-text index for this milestone.
- **nearby uses Haversine formula**: Implemented as a SQL expression in PostgreSQL. No PostGIS dependency required.
- **Recommendation ranking**: When feature scores exist, rank by weighted average of requested score dimensions (default: equal weight). Fallback to `rating` when no features are present.
- **Schema migration for internal_category**: `Base.metadata.create_all()` does not alter existing tables. A standalone migration script (`scripts/migrate_add_internal_category.py`) adds the column via raw SQL `ALTER TABLE` and runs the backfill.

### sort values (enumerated)

| Value | Applies to |
|---|---|
| `rating_desc` | search, nearby, recommend (default) |
| `user_rating_count_desc` | search, nearby, recommend |
| `distance_asc` | nearby only |

Unsupported sort values return HTTP 422.

---

## Functional Requirements

### FR-1 Search API

The system shall provide `GET /api/v1/places/search` for filtering places by structured conditions.

Supported filters: `district`, `internal_category`, `primary_type`, `keyword`, `min_rating`, `max_budget_level`, `indoor`, `open_now`, `sort`, `limit`, `offset`.

Returns a compact candidate list suitable for LLM consumption.

### FR-2 Category abstraction

The system shall define an internal category layer to reduce Google place type fragmentation.

Supported values: `attraction`, `food`, `shopping`, `lodging`, `transport`, `nightlife`, `other`.

The mapping is deterministic and documented. In case of ambiguity, priority order applies (see data-model.md).

`internal_category` is exposed in all retrieval API responses.

### FR-3 Nearby API

The system shall provide `GET /api/v1/places/nearby` for coordinate-based retrieval.

Required: `lat`, `lng`, `radius_m` (1–10000 m). Optional filters: `internal_category`, `primary_type`, `min_rating`, `max_budget_level`, `limit`, `sort`.

Results ordered by `distance_asc` by default. `distance_m` included in each result.

### FR-4 Batch detail API

The system shall provide `POST /api/v1/places/batch`.

Accepts a list of place IDs. Returns detailed normalized records for each valid ID. Unknown IDs are silently omitted. Response preserves request order.

### FR-5 Recommendation API

The system shall provide `POST /api/v1/places/recommend`.

Filters by: `districts`, `internal_category`, `min_rating`, `max_budget_level`, `indoor`, `open_now`, `limit`.

When `internal_category` is not provided, the endpoint defaults to `["attraction", "food", "shopping", "lodging"]` to exclude transport and parking POIs from general recommendations.

When `PlaceFeatures` exist, applies lightweight ranking using available scores. Fallback to `rating` when no feature scores are present.

### FR-6 Statistics API

The system shall provide `GET /api/v1/places/stats`.

Returns: place count by district, place count by internal_category, place count by primary_type.

### FR-7 Categories metadata

The system shall provide `GET /api/v1/places/categories`.

Returns: supported internal category values and representative primary types for each.

### FR-8 Response consistency

All new endpoints return schemas consistent with the existing place service. Pagination uses `limit`/`offset` with a `total` count in the response envelope.

### FR-9 Taipei-only constraint

All new APIs operate only on the normalized `places` table. No endpoint reads from `place_source_google` for user-facing retrieval.

### FR-10 Backward compatibility

Existing `GET /api/v1/places` and `GET /api/v1/places/{place_id}` behavior must remain unchanged.

---

## User Stories

### US-1 Candidate retrieval for LLM

As the main backend LLM, I want to search places by district, category, and rating so that I can build a candidate list for recommendations.

### US-2 Nearby lookup for contextual recommendations

As the main backend LLM, I want to retrieve nearby places around a coordinate so that I can suggest places close to a chosen location.

### US-3 Batch detail lookup

As the main backend LLM, I want to retrieve detailed information for multiple places in one request so that I do not need to make many single-place API calls.

### US-4 Category simplification

As the main backend LLM, I want internal categories such as `food` or `attraction` so that I do not need to interpret fragmented Google place types directly.

### US-5 Backend recommendation primitive

As the main backend LLM, I want a backend recommendation endpoint so that I can ask the data layer for high-quality candidates instead of manually scoring raw rows.

### US-6 Dataset visibility

As a developer, I want statistics endpoints so that I can inspect the current shape of the place dataset and verify whether retrieval behavior is balanced.

---

## Acceptance Criteria

- **AC-1**: `GET /places/search` with valid filters returns matching places with pagination metadata.
- **AC-2**: All retrieval responses contain a valid `internal_category` value for each place.
- **AC-3**: `GET /places/nearby` with valid coordinates returns places within radius; each result includes `distance_m`.
- **AC-4**: `POST /places/batch` with valid IDs returns detailed records in request order; unknown IDs are omitted.
- **AC-5**: `POST /places/recommend` returns a ranked or prefiltered candidate list; feature-score ranking is applied when scores exist.
- **AC-6**: `GET /places/stats` returns counts by district, internal_category, and primary_type.
- **AC-7**: No retrieval API reads from `place_source_google`.
- **AC-8**: `GET /api/v1/places` and `GET /api/v1/places/{place_id}` return identical responses before and after this feature lands.

---

## Edge Cases

- `primary_type` is null → `internal_category` falls back to `other`.
- `rating` is null → excluded from `min_rating` filtered results.
- `budget_level` is null → excluded from `max_budget_level` filtered results.
- Empty search result → returns `{"items": [], "total": 0}`, not 404.
- `radius_m` > 10000 → return HTTP 422 with message "radius_m must not exceed 10000".
- Invalid coordinates (lat outside ±90 or lng outside ±180) → HTTP 422.
- `POST /batch` with all unknown IDs → returns `{"items": []}`, not 404.
- `open_now=true` on a place with no opening hours data → place is excluded.
- Unsupported `sort` value → HTTP 422.

---

## Constraints

- Must preserve current Taipei-only ingestion assumptions.
- Must not break current `GET /api/v1/places` or `GET /api/v1/places/{place_id}`.
- Must not require itinerary logic.
- Query performance must remain acceptable on current PostgreSQL dataset (no PostGIS).
- No new external dependencies beyond what is already in `requirements.txt` (except `geopy` if needed for Haversine — prefer pure SQL approach).
