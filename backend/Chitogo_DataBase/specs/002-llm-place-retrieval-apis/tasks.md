# Tasks: LLM-friendly Place Retrieval APIs

**Input**: Design documents from `specs/002-llm-place-retrieval-apis/`
**Prerequisites**: spec.md ✓ plan.md ✓ data-model.md ✓ contracts/api.md ✓ quickstart.md ✓
**Branch**: `feature/llm-place-retrieval-apis`
**Depends on**: `001-place-data-service` complete

**Tests**: pytest in `tests/`. Verification via quickstart.md curl steps.

---

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[US#]**: Maps to user story from spec.md

---

## Phase 1: Schema + Category Normalization

**Purpose**: Add `internal_category` to the DB and wire it into ingestion. Everything downstream depends on this.

**⚠️ CRITICAL**: No endpoint work can begin until T003 (migration) completes successfully.

- [ ] T001 Implement `app/services/category.py` — `CATEGORY_MAP: dict[str, str]` (full mapping from data-model.md); `BUDGET_RANK: dict[str, int]` (`PRICE_LEVEL_FREE=0` through `VERY_EXPENSIVE=4`); `map_category(primary_type: str | None, types_json: list | None) -> str`: check `primary_type` first, then iterate `types_json`, return `"other"` as fallback; `budget_rank(budget_level: str | None) -> int | None`: return rank or None if not in map
- [ ] T002 Update `app/models/place.py` — add `internal_category = Column(String(32), nullable=True, index=True)` after `budget_level`; no other changes to this file
- [ ] T003 Implement `scripts/migrate_add_internal_category.py` — (1) `sys.path` setup; (2) import `engine` from `app.db` and `map_category` from `app.services.category`; (3) with `engine.connect() as conn`: check if column exists via `SELECT column_name FROM information_schema.columns WHERE table_name='places' AND column_name='internal_category'`; if not exists: `ALTER TABLE places ADD COLUMN internal_category VARCHAR(32)`; `CREATE INDEX IF NOT EXISTS ix_places_internal_category ON places (internal_category)`; (4) backfill: `SELECT id, primary_type, types_json FROM places WHERE internal_category IS NULL`; for each row call `map_category(row.primary_type, row.types_json)`; `UPDATE places SET internal_category = %s WHERE id = %s`; (5) print count of rows updated; script must be idempotent (re-running is safe)
- [ ] T004 Update `app/services/ingestion.py` — in `ingest_google_place()`, add `"internal_category": map_category(payload.get("primaryType"), payload.get("types"))` to the `place_data` dict (import `map_category` from `app.services.category`); this populates the field on every new ingest and update going forward
- [ ] T005 [P] Define Pydantic schemas in `app/schemas/retrieval.py` — `PlaceCandidateOut` (id, google_place_id, display_name, internal_category, primary_type, district, formatted_address, latitude, longitude, rating, user_rating_count, budget_level, indoor, outdoor, business_status, google_maps_uri — all Optional where nullable; `model_config = {"from_attributes": True}`); `PlaceDetailOut` (all PlaceCandidateOut fields + types_json, price_level, trend_score, confidence_score, website_uri, national_phone_number, opening_hours_json, created_at, updated_at, features: Optional[PlaceFeaturesOut] — reuse existing PlaceFeaturesOut from `app/schemas/place.py`); `NearbyPlaceCandidateOut` (extends PlaceCandidateOut with `distance_m: float`); `ListEnvelope[T]` generic: `items: list[T]`, `total: int`, `limit: int`, `offset: int`; `BatchResponse`: `items: list[PlaceDetailOut]`; `StatsResponse`: `total_places: int`, `by_district: dict[str, int]`, `by_internal_category: dict[str, int]`, `by_primary_type: dict[str, int]`; `CategoryItem`: `value: str`, `label: str`, `representative_types: list[str]`; `CategoriesResponse`: `categories: list[CategoryItem]`

**Checkpoint**: `python scripts/migrate_add_internal_category.py` runs without error. Re-running is a no-op. `internal_category` column exists in `places` table. All seeded rows have non-null `internal_category`.

---

## Phase 2: Search, Nearby, Categories Endpoints

**Purpose**: Core retrieval endpoints. Depends on Phase 1 complete.

- [ ] T006 [US1, US4] Implement `GET /api/v1/places/search` in `app/routers/retrieval.py` — create `router = APIRouter()`; query `Place` with filters: `district` (eq), `internal_category` (eq, validate against allowed values → 422 if invalid), `primary_type` (eq), `keyword` (ilike on `display_name`: `Place.display_name.ilike(f"%{keyword}%")`), `min_rating` (ge), `max_budget_level` (translate via `BUDGET_RANK`: filter `budget_level` IN keys with rank ≤ max, exclude nulls), `indoor` (eq); apply `open_now` filter (Python post-filter: evaluate `opening_hours_json.periods` against `datetime.now(ZoneInfo("Asia/Taipei"))`; exclude places with no periods data); apply `sort` (`rating_desc` → `Place.rating.desc()`, `user_rating_count_desc` → `Place.user_rating_count.desc()`; 422 on unknown sort); apply `limit` (max 100, default 20) and `offset` (default 0); count total with separate `count()` query before applying limit/offset; return `ListEnvelope[PlaceCandidateOut]`
- [ ] T007 [US2] Implement `GET /api/v1/places/nearby` in `app/routers/retrieval.py` — validate `lat` (±90), `lng` (±180), `radius_m` (1–**10000**, hard limit) → 422 on violation with message `"radius_m must not exceed 10000"`; compute bounding box delta (`lat_delta = radius_m / 111320`, `lng_delta = radius_m / (111320 * cos(radians(lat)))`); pre-filter with `Place.latitude.between(lat - lat_delta, lat + lat_delta)` and `Place.longitude.between(lng - lng_delta, lng + lng_delta)`; compute Haversine distance as SQLAlchemy `func` expression or raw `text()`: `(6371000 * acos(cos(radians(:lat)) * cos(radians(Place.latitude)) * cos(radians(Place.longitude) - radians(:lng)) + sin(radians(:lat)) * sin(radians(Place.latitude))))` aliased as `distance_m`; apply optional filters: `internal_category`, `primary_type`, `min_rating`, `max_budget_level`; apply sort (`distance_asc` by default → ORDER BY distance_m ASC; also allow `rating_desc`, `user_rating_count_desc`; 422 on `distance_asc` used in non-nearby context); apply `limit` (max 100, default 20); return `ListEnvelope[NearbyPlaceCandidateOut]` (include `distance_m` in each item)
- [ ] T008 [US4] Implement `GET /api/v1/places/categories` in `app/routers/retrieval.py` — return static `CategoriesResponse` built from the `CATEGORY_MAP` in `app/services/category.py`; define `CATEGORY_LABELS` and `REPRESENTATIVE_TYPES` dicts in `category.py`; no DB query needed; response is deterministic

**Checkpoint**: `curl /places/search` returns envelope. `curl /places/nearby?lat=25.0441&lng=121.5292&radius_m=1000` returns `distance_m`. `curl /places/categories` returns 7 categories.

---

## Phase 3: Batch + Recommend Endpoints

**Purpose**: LLM-oriented batch and recommendation primitives.

- [ ] T009 [US3] Implement `POST /api/v1/places/batch` in `app/routers/retrieval.py` — request body `BatchRequest(place_ids: list[int])`; validate `len(place_ids) >= 1` and `len(place_ids) <= 100` → 422; query `Place` where `Place.id.in_(place_ids)` and separately query `PlaceFeatures` where `PlaceFeatures.place_id.in_(place_ids)`; build a `features_map: dict[int, PlaceFeatures]`; assemble `PlaceDetailOut` for each id in original `place_ids` order, attaching features if present; silently skip unknown IDs; return `BatchResponse`
- [ ] T010 [US5] Implement `POST /api/v1/places/recommend` in `app/routers/retrieval.py` — request body `RecommendRequest(districts: list[str] | None, internal_category: str | None, min_rating: float | None, max_budget_level: int | None, indoor: bool | None, open_now: bool | None, limit: int = 10)`; validate `limit <= 50` → 422; **if `internal_category` is None, apply default category filter**: `Place.internal_category.in_(["attraction", "food", "shopping", "lodging"])`; apply same filter logic as search (districts as `Place.district.in_(districts)` if provided); apply `open_now` post-filter same as search; load `PlaceFeatures` for all candidate place IDs; rank: for places with features, compute `mean` of non-null score columns (`couple_score`, `family_score`, `food_score`, `culture_score`, `rainy_day_score`, `crowd_score`, `transport_score`, `hidden_gem_score`); sort by `(feature_score DESC NULLS LAST, rating DESC NULLS LAST)`; apply `limit`; return `ListEnvelope[PlaceCandidateOut]`

**Checkpoint**: `POST /places/batch [1]` returns full detail. `POST /places/batch [9999]` returns empty items. `POST /places/recommend {}` returns items sorted by rating (no features yet).

---

## Phase 4: Statistics Endpoint

- [ ] T011 [US6] Implement `GET /api/v1/places/stats` in `app/routers/retrieval.py` — run three aggregate queries: (1) `SELECT count(*) FROM places` for `total_places`; (2) `SELECT district, count(*) FROM places WHERE district IS NOT NULL GROUP BY district ORDER BY count DESC` for `by_district`; (3) `SELECT internal_category, count(*) FROM places GROUP BY internal_category` for `by_internal_category`; (4) `SELECT primary_type, count(*) FROM places WHERE primary_type IS NOT NULL GROUP BY primary_type ORDER BY count DESC` for `by_primary_type`; assemble and return `StatsResponse`

**Checkpoint**: `GET /places/stats` returns dict with all three sections; `by_internal_category` includes all 7 category values that have ≥1 place.

---

## Phase 5: App Wiring + Tests

- [ ] T012 Update `app/main.py` — `from app.routers import retrieval`; `app.include_router(retrieval.router, prefix="/api/v1", tags=["retrieval"])` in lifespan section alongside existing routers; no other changes
- [ ] T013 [P] Implement `tests/test_search.py` — test happy path with no filters; test `district` filter; test `internal_category` filter; test `keyword` ilike; test `min_rating` filter; test `max_budget_level` filter; test pagination (`limit`, `offset`); test invalid sort → 422; test empty result → `{"items":[],"total":0}` not 404
- [ ] T014 [P] Implement `tests/test_nearby.py` — test within radius returns results with `distance_m`; test radius too large → 422; test `lat=999` → 422; test category filter within nearby; test default sort is `distance_asc`
- [ ] T015 [P] Implement `tests/test_batch_recommend.py` — test batch with known ID returns full detail with features; test batch unknown IDs returns empty; test batch order preserved; test recommend with no filters returns results; test recommend `limit` > 50 → 422; test recommend empty result not error
- [ ] T016 [P] Implement `tests/test_stats_categories.py` — test stats returns all three sections; test categories returns 7 items; test categories value names match allowed list
- [ ] T017 Regression verification — run `curl http://localhost:8000/api/v1/places` and confirm response shape unchanged (no `internal_category` added to existing `PlaceListItem`); run `curl http://localhost:8000/api/v1/places/1` and confirm response shape unchanged; run `POST /api/v1/places/import/google` with a new payload and confirm `internal_category` is set correctly in the DB

**Checkpoint**: All 7 quickstart.md steps pass. No existing test regressions. `GET /api/v1/places` still returns `PlaceListItem` schema unchanged.

---

## Dependencies & Execution Order

```
Phase 1 (T001–T005)   → no dependencies; start immediately
  T001: category.py   → must complete before T003, T004
  T002: model update  → must complete before T003
  T003: migration     → must complete before any endpoint work
  T004: ingestion     → depends on T001
  T005: schemas       → [P] parallel with T001–T004

Phase 2 (T006–T008)   → depends on Phase 1 complete
  T006–T008           → [P] parallel (different endpoints, same router file — implement sequentially within file)

Phase 3 (T009–T010)   → depends on Phase 1 complete; [P] parallel with Phase 2
  T009, T010          → can be developed in parallel with T006–T008 if staffed

Phase 4 (T011)        → depends on Phase 1 complete; [P] parallel with Phases 2–3

Phase 5 (T012–T017)   → depends on Phases 2–4 complete
  T012                → must run before tests (wires router)
  T013–T016           → [P] parallel
  T017                → regression; run last
```

---

## Task Summary

| Phase | Tasks | Story | Notes |
|---|---|---|---|
| Phase 1: Schema + Category | T001–T005 | US4 | T005 [P] |
| Phase 2: Search + Nearby + Categories | T006–T008 | US1, US2, US4 | sequential in same file |
| Phase 3: Batch + Recommend | T009–T010 | US3, US5 | [P] with Phase 2 |
| Phase 4: Stats | T011 | US6 | [P] with Phases 2–3 |
| Phase 5: Wiring + Tests | T012–T017 | — | T013–T016 [P] |
| **Total** | **17 tasks** | | **9 parallelizable** |

---

## Notes

- `open_now` filter must use `zoneinfo.ZoneInfo("Asia/Taipei")` — do not use `datetime.utcnow()` or server local time without explicit TZ
- `max_budget_level` filter must exclude rows where `budget_level IS NULL`
- `POST /places/batch` silently omits unknown IDs — never raises 404
- `POST /places/recommend` with empty result returns `{"items":[],"total":0}` — never raises 404
- `internal_category` is NOT added to the existing `PlaceListItem` or `PlaceDetail` schemas — backward compat preserved. Only new `PlaceCandidateOut` and `PlaceDetailOut` schemas include it.
- `scripts/migrate_add_internal_category.py` must be idempotent — check column existence before `ALTER TABLE`
