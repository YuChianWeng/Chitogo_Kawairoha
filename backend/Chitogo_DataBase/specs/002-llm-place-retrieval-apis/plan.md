# Implementation Plan: LLM-friendly Place Retrieval APIs

**Branch**: `feature/llm-place-retrieval-apis` | **Date**: 2026-04-18
**Spec**: [spec.md](spec.md) | **Depends on**: `001-place-data-service`

---

## Summary

Extend the existing FastAPI place data service with six new endpoints optimized for LLM-driven candidate retrieval. All endpoints read from the existing `places` and `place_features` tables. One new column (`internal_category`) is added to `places` via a standalone migration script.

---

## Technical Context

**Language/Version**: Python 3.11+ (no change)
**Framework**: FastAPI + SQLAlchemy 2.x (no change)
**Database**: PostgreSQL 12 (no change)
**New dependencies**: None (Haversine computed in SQL; `open_now` computed in Python)
**Testing**: pytest in `tests/` (existing pattern from 001)
**Schema migration**: standalone `ALTER TABLE` script — Alembic still deferred

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| `internal_category` storage | DB column (indexed) | Enables SQL filter; no per-request mapping overhead |
| Schema migration mechanism | `scripts/migrate_add_internal_category.py` | `create_all` does not alter existing tables; Alembic deferred |
| Nearby geospatial | Haversine in raw SQL | No PostGIS required; dataset is small enough |
| `open_now` | Best-effort Python evaluation | Opening hours JSON format is complex; missing data → excluded |
| `keyword` search | `ilike` on `display_name` | Sufficient for milestone; no FTS index needed |
| Recommendation ranking | Mean of non-null feature scores → fallback rating | Simple, deterministic, no ML needed |

---

## New Files

```text
app/
├── services/
│   └── category.py           ← internal_category mapping + budget rank utilities
├── schemas/
│   └── retrieval.py          ← new Pydantic schemas (PlaceCandidateOut, PlaceDetailOut, etc.)
└── routers/
    └── retrieval.py          ← all 6 new endpoints

scripts/
└── migrate_add_internal_category.py   ← ALTER TABLE + backfill
```

### Modified Files

```text
app/models/place.py           ← add internal_category column
app/models/__init__.py        ← no change (models already imported)
app/main.py                   ← include retrieval router
app/services/ingestion.py     ← populate internal_category on ingest
```

---

## Implementation Order

### Phase 1 — Schema + Category Normalization

| # | File | What |
|---|---|---|
| 1 | `app/services/category.py` | `CATEGORY_MAP`, `BUDGET_RANK`, `map_category()`, `budget_rank()` |
| 2 | `app/models/place.py` | Add `internal_category = Column(String(32), nullable=True, index=True)` |
| 3 | `scripts/migrate_add_internal_category.py` | `ALTER TABLE places ADD COLUMN internal_category ...` + backfill |
| 4 | `app/services/ingestion.py` | Call `map_category()` when building `place_data` dict |
| 5 | `app/schemas/retrieval.py` | `PlaceCandidateOut`, `PlaceDetailOut`, response envelopes |

### Phase 2 — Search + Nearby + Categories

| # | File | What |
|---|---|---|
| 6 | `app/routers/retrieval.py` | `GET /places/search` |
| 7 | `app/routers/retrieval.py` | `GET /places/nearby` (Haversine SQL) |
| 8 | `app/routers/retrieval.py` | `GET /places/categories` (static response from CATEGORY_MAP) |

### Phase 3 — Batch + Recommend

| # | File | What |
|---|---|---|
| 9 | `app/routers/retrieval.py` | `POST /places/batch` |
| 10 | `app/routers/retrieval.py` | `POST /places/recommend` (filter + rank) |

### Phase 4 — Stats

| # | File | What |
|---|---|---|
| 11 | `app/routers/retrieval.py` | `GET /places/stats` (aggregate queries) |

### Phase 5 — App wiring + Tests

| # | File | What |
|---|---|---|
| 12 | `app/main.py` | `include_router(retrieval.router, ...)` |
| 13 | `tests/test_search.py` | search filter tests, pagination, sort |
| 14 | `tests/test_nearby.py` | radius, coord validation, category filter |
| 15 | `tests/test_batch_recommend.py` | batch order, unknown IDs, recommend ranking |
| 16 | `tests/test_stats_categories.py` | stats counts, categories shape |
| 17 | Regression | verify existing list/detail endpoints unchanged |

---

## Risks and Gotchas

| Risk | Mitigation |
|---|---|
| `alter table` on a live table with existing rows | Migration script runs backfill in same transaction; script is idempotent (checks if column exists first) |
| Haversine at large radii returns inaccurate distances | Max radius capped at 50km; acceptable for Taipei POI use case |
| `open_now` timezone: server may not be Asia/Taipei | Compute with `zoneinfo.ZoneInfo("Asia/Taipei")` explicitly |
| Recommend returns 0 results when filters are too strict | Empty list + total=0 is valid; document in quickstart |
| `place_ids` list in batch could be very large | Validate `len(place_ids) <= 100` |
| Backward compat: existing `/places` uses `PlaceListItem` schema | Do not modify `PlaceListItem`; new routes use `PlaceCandidateOut` |
