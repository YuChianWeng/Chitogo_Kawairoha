# Tasks: Social-Crawl Data Ingestion

**Input**: Implementation plan from `specs/003-social-crawl-ingestion/plan.md`
**Prerequisites**: `plan.md` ✓
**Depends on**: `002-llm-place-retrieval-apis` already landed in `backend/Chitogo_DataBase/`; current `backend/Chat_Agent/` place adapter is working

**Tests**: `pytest` in `backend/Chitogo_DataBase/tests/` and `backend/Chat_Agent/tests/`. Manual verification uses the migration, import, and curl commands listed in `plan.md`.

**Organization**: Tasks are grouped into four implementation phases. Each phase is a single executable delivery slice: it can be completed in one pass, leaves both services in a runnable state, and has a concrete acceptance target before the next phase begins.

## Format: `[ID] [P?] Description`

- **[P]**: Can run in parallel with other tasks in the same phase because the write scope is separate
- All file paths are repo-root relative
- Database-service tests stay under `backend/Chitogo_DataBase/tests/` to match the current repo pattern; Chat Agent tests use `backend/Chat_Agent/tests/unit/`

---

## Phase 1: Schema and Persistence Foundation

**Acceptance target**: Running `python3 scripts/migrate_add_social_tables.py` creates the new social-mention table, adds the new `places` columns, is safe to run twice, and does not change any API behavior yet.

**Purpose**: Land the storage layer first so every later phase can build on stable schema primitives.

- [ ] T001 Create `backend/Chitogo_DataBase/app/models/place_social_mention.py` — define `PlaceSocialMention` ORM model with `id`, `place_id` FK to `places.id` (`ondelete="CASCADE"`), `platform`, `source_url`, `original_text`, `sentiment_score` (`Numeric(3,2)`), `crowdedness` (`Numeric(3,2)`), `vibe_tags` (`JSONB`), `posted_at`, `ingested_at` (`server_default=func.now()`), `external_id`; add `UniqueConstraint("platform", "external_id")` and indexes on `place_id` and `platform`; relationship back to `Place`
- [ ] T002 Update `backend/Chitogo_DataBase/app/models/place.py` — add nullable `vibe_tags: JSONB`, non-null `mention_count: Integer` with server default `0`, nullable `sentiment_score: Numeric(3,2)`; add `social_mentions` relationship to `PlaceSocialMention`; keep all existing columns and relationships unchanged
- [ ] T003 Update `backend/Chitogo_DataBase/app/models/__init__.py` — register and export `PlaceSocialMention` alongside `Place`, `PlaceSourceGoogle`, and `PlaceFeatures`
- [ ] T004 Implement `backend/Chitogo_DataBase/scripts/migrate_add_social_tables.py` — mirror the style of `migrate_add_internal_category.py`: bootstrap `sys.path`, open a SQLAlchemy connection, introspect `information_schema`, create `place_social_mentions` plus indexes if missing, add missing `places.vibe_tags`, `places.mention_count`, `places.sentiment_score` columns and `ix_places_mention_count` if missing, print what changed, and remain idempotent on re-run

**Checkpoint**: The migration script runs twice without error, `place_social_mentions` exists, the three new `places` columns exist, and the existing service still boots without endpoint regressions.

---

## Phase 2: CSV Import and Social Aggregation

**Acceptance target**: `python3 scripts/import_crawl_csv.py tests/fixtures/social/ifoodie_sample.csv --source ifoodie --no-enrich` imports sample rows, inserts or matches places, writes `place_social_mentions`, computes aggregates, and a second run is a no-op for duplicate mentions.

**Purpose**: Deliver a complete offline ingestion path from crawler CSVs into normalized place rows and social aggregates before touching retrieval APIs.

- [ ] T005 Implement `backend/Chitogo_DataBase/app/services/social_ingestion.py` — add `CrawlMention` / `ImportStats` dataclasses plus `import_crawl_csv(db, csv_path, *, source_hint=None, google_client=None) -> ImportStats`; parse CSV with `encoding="utf-8-sig"` and `csv.DictReader`; normalize `platform`, `external_id`, `posted_at`, `sentiment_score`, `crowdedness`, and `vibe_tags` (support both JSON-array and comma-separated formats); reject rows without Google Place ID; resolve places in ordered tiers: existing DB row by `google_place_id`, Google Details enrichment through the existing Google ingestion path when enabled, otherwise fallback minimal insert using Taipei district regex over `TAIPEI_ALLOWED_DISTRICTS`; when district cannot be confirmed, preserve a raw source record using the existing append-only raw-record path and count the row as `filtered_out`
- [ ] T006 Implement `backend/Chitogo_DataBase/app/services/social_aggregation.py` — add `recompute_social_aggregates(db, place_ids: Iterable[int] | None = None) -> None`; aggregate per place from `place_social_mentions`: `mention_count`, mean `sentiment_score`, mean `crowdedness` into `place_features.crowd_score`, top-12 `vibe_tags` by frequency with recency tie-break, and `trend_score` using a 7-day half-life decay normalized into the existing `Numeric(5,4)` range; make the function safe to re-run and able to recompute only touched places
- [ ] T007 Implement `backend/Chitogo_DataBase/scripts/import_crawl_csv.py` — CLI entry point `python3 scripts/import_crawl_csv.py <csv_path> [--source ifoodie|taipei_spots] [--no-enrich]`; load `.env`, open a DB session, call `import_crawl_csv()`, print the counters `{db_hit, google_enriched, fallback_inserted, filtered_out, duplicate_mention, error}`, and exit non-zero only on fatal setup errors
- [ ] T008 [P] Create social fixtures under `backend/Chitogo_DataBase/tests/fixtures/social/` — add `ifoodie_sample.csv` and `taipei_spots_sample.csv` with 5–8 representative rows each covering: DB hit, Google-enriched miss, fallback insert, filtered-out non-Taipei row, duplicate mention, JSON-array tags, comma-separated tags
- [ ] T009 [P] Add `backend/Chitogo_DataBase/tests/test_social_ingestion_parse.py` — cover dialect parsing, platform normalization, tag normalization, timestamp parsing, missing Google Place ID rejection, and source-hint handling
- [ ] T010 [P] Add `backend/Chitogo_DataBase/tests/test_social_fallback_district.py` and `backend/Chitogo_DataBase/tests/test_social_aggregation.py` — district-regex extraction over Taipei / non-Taipei addresses; aggregation expectations for `mention_count`, averaged sentiment / crowd, top tags, trend decay, and idempotent recompute
- [ ] T011 Add `backend/Chitogo_DataBase/tests/test_import_crawl_csv.py` — integration-style import test using the fixture CSVs and a stubbed Google client; assert place upsert behavior, mention insert behavior, aggregate refresh, duplicate protection from `(platform, external_id)`, and re-run idempotency

**Checkpoint**: Sample CSV imports complete end-to-end, mention rows are persisted, affected place aggregates are populated, and repeating the same import does not duplicate mentions.

---

## Phase 3: Place Data Service API Extensions

**Acceptance target**: `GET /api/v1/places/search?vibe_tag=hidden_gem&limit=5` filters correctly, `GET /api/v1/places/search?sort=mention_count_desc&limit=5` sorts correctly, and `GET /api/v1/places/{id}` can include the latest social mentions without breaking existing clients.

**Purpose**: Make the ingested social signals queryable and serializable from the existing Place Data Service before changing the Chat Agent.

- [ ] T012 Update `backend/Chitogo_DataBase/app/schemas/place.py` — add a small `MentionOut` schema for recent social evidence; extend `PlaceDetail` with optional `vibe_tags`, `mention_count`, `sentiment_score`, and `recent_mentions`; extend `PlaceListItem` with the same optional social summary fields so `/api/v1/places` and `/api/v1/places/{id}` expose a consistent shape without making any of the new fields required
- [ ] T013 Update `backend/Chitogo_DataBase/app/schemas/retrieval.py` — extend `PlaceSearchSort` with `mention_count_desc`, `trend_score_desc`, and `sentiment_desc`; extend `PlaceCandidateOut` with optional `vibe_tags`, `mention_count`, `sentiment_score`, `trend_score`, and `crowd_score`; keep all new fields optional for backward compatibility
- [ ] T014 Update `backend/Chitogo_DataBase/app/services/place_search.py` — extend `PlaceSearchParams` with `vibe_tags: list[str] | None` and `min_mentions: int | None`; implement AND semantics for repeatable `vibe_tag` filters via `Place.vibe_tags.contains([tag])`; filter `Place.mention_count >= min_mentions`; add social sorts to `apply_place_search_sort()` while preserving existing rating-based behavior
- [ ] T015 Update `backend/Chitogo_DataBase/app/routers/places.py` — accept repeatable `vibe_tag` query params and optional `min_mentions`; pass them into `PlaceSearchParams`; ensure `/places/search` and `/places/recommend` serialize the new optional social fields through `PlaceCandidateOut`; extend `/places/{place_id}` to load the latest five `PlaceSocialMention` rows ordered by `posted_at DESC` and expose them as optional `recent_mentions`
- [ ] T016 [P] Add `backend/Chitogo_DataBase/tests/test_search_vibe_tag_filter.py` — seed places with different tag combinations and assert repeated `vibe_tag` params use intersection semantics rather than union semantics
- [ ] T017 [P] Add `backend/Chitogo_DataBase/tests/test_search_new_sorts.py` and `backend/Chitogo_DataBase/tests/test_place_detail_recent_mentions.py` — verify ordering for `mention_count_desc`, `trend_score_desc`, and `sentiment_desc`; verify `GET /places/{id}` returns only the latest five mentions in descending recency
- [ ] T018 Update `backend/Chitogo_DataBase/CLAUDE.md` — add a short recent-changes note covering the new migration script, import CLI, social search params, and new sorts so local operators do not miss the feature surface

**Checkpoint**: The Data Service can filter and sort on social signals, detail responses can expose recent mention evidence, and all new fields remain optional so existing callers stay compatible.

---

## Phase 4: Chat Agent Passthrough and Contract Coverage

**Acceptance target**: `PlaceToolAdapter.search_places(vibe_tags=["romantic"], sort="trend_score_desc")` sends repeated `vibe_tag` query params, the returned `ToolPlace` includes the new social fields, and existing adapter tests still pass.

**Purpose**: Finish the end-to-end delivery so the LLM-facing Chat Agent can consume the new social signals without any prompt rewrite.

- [ ] T019 Update `backend/Chat_Agent/app/tools/models.py` — extend `PlaceSort` to include `mention_count_desc`, `trend_score_desc`, and `sentiment_desc`; extend `ToolPlace` with optional `vibe_tags: list[str] | None`, `mention_count: int | None`, and `sentiment_score: float | None`; keep `model_config = ConfigDict(extra="forbid")`
- [ ] T020 Update `backend/Chat_Agent/app/tools/place_adapter.py` — extend `search_places()` to accept `vibe_tags: list[str] | None` and `min_mentions: int | None`; emit repeated `vibe_tag` query params when tags are present; forward `min_mentions` and the new social sort values; pass `vibe_tags`, `mention_count`, and `sentiment_score` through `_normalize_place()` into `ToolPlace`
- [ ] T021 [P] Add `backend/Chat_Agent/tests/unit/test_place_adapter_social_fields.py` — mock Data Service responses containing `vibe_tags`, `mention_count`, and `sentiment_score`; assert normalization into `ToolPlace` and backward compatibility when the fields are missing
- [ ] T022 [P] Add `backend/Chat_Agent/tests/unit/test_place_adapter_vibe_tag_param.py` — assert `search_places(vibe_tags=["romantic", "scenic"], min_mentions=3, sort="trend_score_desc")` emits the expected repeated query params and forwards the new sort untouched
- [ ] T023 Update `backend/Chat_Agent/CLAUDE.md` — add a short recent-changes note documenting the new adapter search arguments and the extra social fields available on `ToolPlace`

**Checkpoint**: The Chat Agent adapter has full request / response parity with the new Data Service social-search surface, and the structured place model exposes the social signals to downstream LLM code.

---

## Dependencies and Execution Order

### Phase dependencies

```
Phase 1: Schema and Persistence Foundation
  No dependencies. Must land first.

Phase 2: CSV Import and Social Aggregation
  Depends on Phase 1 schema objects and migration being complete.

Phase 3: Place Data Service API Extensions
  Depends on Phase 1 for schema, and should follow Phase 2 so the API can be verified against real imported social data.

Phase 4: Chat Agent Passthrough and Contract Coverage
  Depends on Phase 3 because it mirrors the new Data Service API surface.
```

### Within-phase parallel opportunities

- **Phase 2**: T008, T009, and T010 can run in parallel after T005–T007 skeletons exist
- **Phase 3**: T016 and T017 can run in parallel after T012–T015 land
- **Phase 4**: T021 and T022 can run in parallel after T019–T020 land

---

## Recommended Delivery Strategy

1. **Phase 1** as a schema-only PR: minimal risk, no runtime behavior change
2. **Phase 2** as the ingestion PR: operator-facing CLI plus idempotent aggregate refresh
3. **Phase 3** as the retrieval PR: query / sort / detail surface for Data Service consumers
4. **Phase 4** as the Chat Agent PR: adapter passthrough and contract tests

This preserves the rollout sequence already proposed in `plan.md`, but each phase now has a tighter acceptance target and a bounded execution scope.

---

## Task Summary

| Phase | Tasks | Outcome |
|---|---|---|
| Phase 1: Schema and Persistence Foundation | T001–T004 | Social tables and columns exist, migration is idempotent |
| Phase 2: CSV Import and Social Aggregation | T005–T011 | CSVs import into DB, mentions persist, aggregates refresh |
| Phase 3: Place Data Service API Extensions | T012–T018 | Social fields are searchable and serializable from the Data Service |
| Phase 4: Chat Agent Passthrough and Contract Coverage | T019–T023 | Chat Agent can request and consume the new social signals |
| **Total** | **23 tasks** | **4 independently executable phases** |

---

## Notes

- The plan's raw-evidence fallback remains intact: rows that cannot be confirmed to be in Taipei are retained as raw source evidence and counted as `filtered_out`, but they do not create normalized `places` or `place_social_mentions` rows
- `vibe_tags` filtering should use JSONB array containment with AND semantics across repeated query params
- Aggregation is intentionally re-runnable; never couple it to a one-time migration
- All new API fields are optional to preserve compatibility with existing clients and with `ToolPlace.extra="forbid"`
