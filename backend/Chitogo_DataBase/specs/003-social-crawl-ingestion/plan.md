# Implementation Plan: Social-Crawl Data Ingestion

Feature: 003-social-crawl-ingestion
Services touched: `backend/Chitogo_DataBase/` (primary), `backend/Chat_Agent/` (consumer)
Author: ChitoGo team
Last updated: 2026-04-24

---

## 1. Goal

Import two crawler CSV datasets
(`backend/Chitogo_DataBase/taipei_spots.csv`,
`backend/Chitogo_DataBase/ifoodie.csv`) into the Place Data Service so that
the Chat Agent can retrieve them through the existing HTTP tools and use the
new social signals (`vibe_tags`, `sentiment_score`, `crowdedness`,
`mention_count`) when recommending Taipei venues.

Success criteria:

- Every row of both CSVs is either (a) merged into an existing `places`
  record, or (b) inserted as a new `places` row, or (c) kept as raw evidence
  when the venue cannot be confirmed to be in Taipei.
- Per-post evidence (text, URL, platform, timestamp) is preserved in a new
  `place_social_mentions` table.
- `/api/v1/places/search` can filter by `vibe_tag` and sort by
  `mention_count_desc` / `trend_score_desc`.
- The Chat Agent's `ToolPlace` exposes `vibe_tags`, `mention_count`, and
  `sentiment_score` so the LLM can cite them.
- All existing tests keep passing; new ingestion has coverage from fixture
  CSVs.

Non-goals:

- Building a live crawler. The CSVs are the input contract.
- Replacing the Google-Places-based ingestion; this plan extends it.
- Deduplicating near-duplicate venues that have different
  `google_place_id`s.

---

## 2. Input Data Summary

| CSV | Rows | Unique `google_place_id` | Key fields | Notes |
|-----|-----:|-------------------------:|------------|-------|
| `taipei_spots.csv` | 67 | 64 | `id, platform, location, sentiment_score, crowdedness, vibe_tags (JSON array), original_text, source_url, created_at, address, place_id` | `platform ∈ {Threads, Instagram, Reddit}`. `place_id` holds the Google Place ID. |
| `ifoodie.csv` | 804 | 529 | `id, platform, location, address, google_place_id, sentiment_score, crowdedness, vibe_tags (comma string), original_text, source_url, created_at` | `platform = "ifoodie"`. |

- Cross-CSV overlap: 3 shared Google Place IDs; total unique venues across
  both files ≈ 590.
- **Missing fields** compared to the current `ingest_google_place()`
  contract: `displayName`, `addressComponents`, `location.lat/lng`,
  `primaryType`, `types`, `rating`, `userRatingCount`, `priceLevel`,
  `regularOpeningHours`, `googleMapsUri`, `websiteUri`,
  `nationalPhoneNumber`.
- **New fields** the existing schema has no home for: `sentiment_score`,
  `crowdedness`, `vibe_tags`, `original_text`, `source_url`, `platform`,
  `created_at`.

Current `ingest_google_place()` hard-filters rows without a Taipei district
derived from `addressComponents`, so a direct feed would discard every CSV
row.

---

## 3. Data Model Changes

### 3.1 New table: `place_social_mentions`

Stores one row per crawled post, so the raw evidence remains queryable and
future re-aggregation is possible.

```sql
CREATE TABLE place_social_mentions (
    id              SERIAL PRIMARY KEY,
    place_id        INTEGER NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    platform        VARCHAR(32) NOT NULL,       -- threads | instagram | reddit | ifoodie | ...
    source_url      VARCHAR(1024),
    original_text   TEXT,
    sentiment_score NUMERIC(3,2),               -- 0.00–1.00
    crowdedness     NUMERIC(3,2),               -- 0.00–1.00
    vibe_tags       JSONB,                      -- list[str]
    posted_at       TIMESTAMPTZ,                -- from CSV created_at
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    external_id     VARCHAR(128),               -- CSV `id`, for idempotency
    UNIQUE (platform, external_id)
);
CREATE INDEX ix_social_mentions_place_id ON place_social_mentions (place_id);
CREATE INDEX ix_social_mentions_platform ON place_social_mentions (platform);
```

Idempotency: `UNIQUE (platform, external_id)` means re-running the import
does not duplicate rows.

### 3.2 Extend `places`

Add three columns so Chat Agent queries do not need to join the mentions
table for common filters:

```sql
ALTER TABLE places ADD COLUMN vibe_tags        JSONB;
ALTER TABLE places ADD COLUMN mention_count    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE places ADD COLUMN sentiment_score  NUMERIC(3,2);

CREATE INDEX ix_places_mention_count ON places (mention_count);
-- GIN index only if we later need vibe_tag containment queries at scale:
-- CREATE INDEX ix_places_vibe_tags_gin ON places USING GIN (vibe_tags);
```

`places.crowd_score` reuses the existing `place_features.crowd_score`
(Numeric(5,4)). `places.trend_score` also already exists and gets rewritten
by the aggregation pass (see §5).

### 3.3 Migration script

`backend/Chitogo_DataBase/scripts/migrate_add_social_tables.py` — mirrors
the style of `migrate_add_internal_category.py`: opens a SQLAlchemy
connection, issues the DDL above, and is idempotent (`IF NOT EXISTS` /
introspect + skip).

---

## 4. Ingestion Pipeline

### 4.1 Overview

```
CSV file ──┐
           │
           ▼
   import_crawl_csv.py (CLI)
           │
           ▼
   SocialIngestionService
     ├─ parse_row()                   # normalize fields, CSV dialect
     ├─ resolve_place(google_id)      # lookup or enrich
     │     ├─ DB hit           → return Place
     │     ├─ Google Details    → ingest_google_place() (existing path)
     │     └─ fallback          → minimal insert
     ├─ insert_mention()
     └─ refresh_aggregates()         # one-shot at end of run
```

### 4.2 New module: `app/services/social_ingestion.py`

Public entry point:

```python
def import_crawl_csv(
    db: Session,
    csv_path: Path,
    *,
    source_hint: Literal["ifoodie", "taipei_spots"] | None = None,
    google_client: GooglePlacesClient | None = None,
) -> ImportStats
```

Steps per CSV row:

1. **Normalize row** into a typed `CrawlMention` dataclass
   (`google_place_id`, `display_name`, `address`, `platform`,
   `source_url`, `original_text`, `sentiment_score`, `crowdedness`,
   `vibe_tags: list[str]`, `posted_at`, `external_id`).
   - `vibe_tags` parser auto-detects JSON array vs. comma-separated string;
     tags are lower-cased and stripped.
   - `platform` lower-cased (`Threads → threads`, etc.).
2. **Resolve the place** (ordered tiers):
   - **Tier A — DB hit**: `db.query(Place).filter_by(google_place_id=...)`
     returns existing row → use it.
   - **Tier B — Google Places Details** (if `GOOGLE_MAPS_API_KEY` set and
     row was not in DB): call Places API v1 `places/{id}` with the field
     mask used by `fetch_google_nearby.py` (`id, displayName, primaryType,
     types, formattedAddress, addressComponents, location, rating,
     userRatingCount, priceLevel, businessStatus, googleMapsUri,
     websiteUri, nationalPhoneNumber, regularOpeningHours`), then call the
     existing `ingest_google_place(db, payload)`.
   - **Tier C — Fallback insert** (no key or Google call failed):
     - Extract district from `address` via regex over
       `TAIPEI_ALLOWED_DISTRICTS`.
     - If no Taipei district can be derived → record a
       `PlaceSourceGoogle` raw row only, skip the mention. Matches the
       current "filtered_out" behavior.
     - Otherwise insert a minimal `Place` row: `display_name=location`,
       `formatted_address=address`, `district=<regex match>`,
       `internal_category="other"`, everything else NULL.
3. **Insert mention** into `place_social_mentions`, skipping duplicates by
   `(platform, external_id)`.
4. **Accumulate stats**: counts for
   `{db_hit, google_enriched, fallback_inserted, filtered_out,
   duplicate_mention, error}`.

### 4.3 CLI: `scripts/import_crawl_csv.py`

```
Usage: python scripts/import_crawl_csv.py <csv_path> [--source ifoodie|taipei_spots] [--no-enrich]
```

- Reads config from the same `.env` as the service (`DATABASE_URL`,
  `GOOGLE_MAPS_API_KEY`).
- `--no-enrich` forces Tier A or C (useful for dry-runs without burning
  Google quota).
- Prints a summary in the same shape as `fetch_google_nearby.py`.

### 4.4 Cost & quota

~590 unique venues × ~1 Places Details call = ~590 requests, well inside
the standard Google Places free tier. Enrichment is cached by DB hit, so
repeated runs are free.

---

## 5. Aggregation Pass

Runs once at the end of every import. Lives in
`app/services/social_aggregation.py`:

```python
def recompute_social_aggregates(db: Session, place_ids: Iterable[int] | None = None) -> None:
    # For each affected place:
    #   mentions      = SELECT * FROM place_social_mentions WHERE place_id = ?
    #   mention_count = len(mentions)
    #   sentiment     = mean(m.sentiment_score for m if not null)
    #   crowd         = mean(m.crowdedness   for m if not null)  → place_features.crowd_score
    #   vibe_tags     = top-N tags by frequency (N=12), lower-cased, deduped
    #   trend_score   = sum(0.5 ** age_days(m.posted_at) for m)   # exponential decay
    # Upsert into places.* and place_features.crowd_score.
```

Design decisions:

- `vibe_tags` is top-12 to cap payload size; ties broken by recency.
- `trend_score` uses a 7-day half-life so that fresher mentions dominate;
  the stored value is normalized to `[0,1]` per batch so the existing
  `Numeric(5,4)` column is enough.
- Re-runnable and idempotent. Safe to call after any subset of imports.

---

## 6. API Changes

### 6.1 Place Data Service

**`app/schemas/retrieval.py` — `PlaceCandidateOut`** (add fields, all
optional for backward compatibility):

```python
vibe_tags: list[str] | None = None
mention_count: int | None = None
sentiment_score: float | None = None
trend_score: float | None = None
crowd_score: float | None = None
```

**`GET /api/v1/places/search` (`app/routers/places.py`)** — add:

```
vibe_tag:     list[str] | None   # repeatable; AND semantics
min_mentions: int | None         # ≥
sort:         ...
             | "mention_count_desc"
             | "trend_score_desc"
             | "sentiment_desc"
```

Implementation in `app/services/place_search.py`:

- `if params.vibe_tags: query = query.filter(Place.vibe_tags.contains(tag) for tag in params.vibe_tags)`
  — SQLAlchemy `JSONB.contains([tag])` for each requested tag, ANDed via
  chained `filter()`.
- Sort options go through `apply_place_search_sort`.

**`/api/v1/places/recommend`** — reuse the same new fields; scoring can
optionally blend `trend_score` (future work, out of scope for this plan).

**`/api/v1/places/{place_id}`** — `PlaceDetail` gets an optional
`recent_mentions: list[MentionOut]` field, hydrated via a cheap join
(latest 5 rows by `posted_at DESC`). Non-breaking because it is optional.

### 6.2 Chat Agent

- `backend/Chat_Agent/app/tools/models.py` — `ToolPlace` gains three
  optional fields: `vibe_tags: list[str] | None`, `mention_count: int |
  None`, `sentiment_score: float | None`. `model_config = extra="forbid"`
  is preserved, so the adapter must only set keys that are declared.
- `backend/Chat_Agent/app/tools/place_adapter.py` — `_normalize_place`
  passes the three new keys through, and `search_places()` accepts
  `vibe_tags: list[str] | None = None` plus the new `sort` options. The
  adapter simply forwards them via `_compact_dict`; the server rejects
  unknown sorts, so there is no frontend break.
- No prompt/LLM changes required for phase 1; the LLM can already read the
  serialized `ToolPlace` because new fields are part of the structured
  output.

---

## 7. Testing Plan

### 7.1 Unit tests

- `tests/unit/test_social_ingestion_parse.py`
  - Parses both CSV dialects (JSON-array vs. comma tags).
  - Normalizes platform casing, strips whitespace, lowercases tags.
  - Rejects rows missing `google_place_id`.

- `tests/unit/test_social_aggregation.py`
  - Fixed mention list → expected `vibe_tags`, `mention_count`,
    `sentiment_score`, `crowd_score`, `trend_score`.
  - Idempotency: running `recompute_social_aggregates` twice yields the
    same result.

- `tests/unit/test_social_fallback_district.py`
  - Regex extraction over sample CSV addresses (e.g. `106臺北市大安區...`
    → `大安區`, `208新北市金山區...` → `None`).

### 7.2 Integration tests (Postgres via existing fixture)

- `tests/integration/test_import_crawl_csv.py`
  - Uses truncated fixture files (5 rows each) under
    `tests/fixtures/social/`.
  - Ingestion with Google enrichment stubbed via a fake client.
  - Asserts: places upserted, mentions inserted, aggregates populated,
    re-run is a no-op.

- `tests/integration/test_search_vibe_tag_filter.py`
  - Seeds two places with different `vibe_tags`; asserts
    `GET /places/search?vibe_tag=romantic&vibe_tag=scenic` returns the
    intersection.

- `tests/integration/test_search_new_sorts.py`
  - Asserts ordering by `mention_count_desc` and `trend_score_desc`.

### 7.3 Chat Agent contract tests

- `backend/Chat_Agent/tests/unit/test_place_adapter_social_fields.py`
  - Mock httpx response with new fields; assert they surface on
    `ToolPlace`.
- `backend/Chat_Agent/tests/unit/test_place_adapter_vibe_tag_param.py`
  - Asserts `search_places(vibe_tags=["romantic"])` sends repeated
    `vibe_tag=romantic` query params.

### 7.4 Manual verification

```bash
# Migrate
python scripts/migrate_add_social_tables.py

# Import (dry first)
python scripts/import_crawl_csv.py ifoodie.csv --source ifoodie --no-enrich
python scripts/import_crawl_csv.py taipei_spots.csv --source taipei_spots

# Verify via API
curl 'http://localhost:8000/api/v1/places/search?vibe_tag=hidden_gem&limit=5'
curl 'http://localhost:8000/api/v1/places/search?sort=mention_count_desc&limit=5'
```

---

## 8. Rollout

1. **PR 1 — Schema + migration** (`migrate_add_social_tables.py`,
   SQLAlchemy models updated, no behavior change).
2. **PR 2 — Ingestion service + CLI** (covered by unit + integration
   tests; no API change yet).
3. **PR 3 — API surface extension** (`PlaceCandidateOut`, search filter,
   new sorts). Backward compatible because all new fields are optional.
4. **PR 4 — Chat Agent passthrough** (`ToolPlace`, adapter params).
5. **Data load** on the target environment:
   `python scripts/import_crawl_csv.py ifoodie.csv` →
   `python scripts/import_crawl_csv.py taipei_spots.csv`.
6. **Smoke test** the Chat Agent end-to-end with a prompt such as
   "Find a romantic hidden gem in 信義區".

Each PR is independently revertable because later steps only depend on
schema + model changes landing first.

---

## 9. Open Decisions

| # | Question | Default recommendation |
|---|----------|------------------------|
| 1 | Should we spend Google Places Details quota to enrich new venues? | **Yes, with cache.** ~590 lookups, one-time. Without it, most new places lack `lat/lng` and `primary_type`, breaking `/nearby` and category filters. |
| 2 | `sentiment_score`: new column on `places` vs. inside `place_features.feature_json`? | **New column.** Chat-Agent filters and sorts on it; column access is cheaper than JSONB path. |
| 3 | Recompute aggregates per import, or nightly cron? | **Per import.** Dataset is small; immediate consistency is simpler than scheduling a cron. |
| 4 | Deduplicate near-identical places (same name, different Google IDs)? | **Out of scope.** Tracked separately; we trust `google_place_id` as the key. |
| 5 | Retention of `place_source_google` raw rows from fallback inserts? | **Keep.** Consistent with current behavior and useful when we later enrich them. |

---

## 10. Risks and Mitigations

- **Rate-limit or auth error on Google Places Details during import.**
  Mitigation: per-row try/except, fall back to Tier C, log and continue;
  re-run later to backfill.
- **CSV encoding surprises (BOM, mixed quoting).** Mitigation: open with
  `encoding="utf-8-sig"` and `csv.DictReader`. Fixture tests cover both
  files.
- **`vibe_tags` cardinality explosion.** Mitigation: cap aggregated tags
  at 12 per place; raw tags still live on `place_social_mentions` for
  analysis.
- **Back-compat with existing `PlaceCandidateOut` consumers.**
  Mitigation: all new fields are `Optional` with `None` default;
  `ToolPlace` keeps `extra="forbid"` by only adding declared fields.
- **Double-import of same CSV.** Mitigation:
  `UNIQUE (platform, external_id)` on mentions;
  `ingest_google_place` is already upsert-by-google-place-id.

---

## 11. File Checklist

New:

- `backend/Chitogo_DataBase/app/models/place_social_mention.py`
- `backend/Chitogo_DataBase/app/services/social_ingestion.py`
- `backend/Chitogo_DataBase/app/services/social_aggregation.py`
- `backend/Chitogo_DataBase/scripts/migrate_add_social_tables.py`
- `backend/Chitogo_DataBase/scripts/import_crawl_csv.py`
- `backend/Chitogo_DataBase/tests/fixtures/social/ifoodie_sample.csv`
- `backend/Chitogo_DataBase/tests/fixtures/social/taipei_spots_sample.csv`
- `backend/Chitogo_DataBase/tests/integration/test_import_crawl_csv.py`
- `backend/Chitogo_DataBase/tests/integration/test_search_vibe_tag_filter.py`
- `backend/Chitogo_DataBase/tests/unit/test_social_ingestion_parse.py`
- `backend/Chitogo_DataBase/tests/unit/test_social_aggregation.py`
- `backend/Chat_Agent/tests/unit/test_place_adapter_social_fields.py`

Modified:

- `backend/Chitogo_DataBase/app/models/__init__.py` (register new model)
- `backend/Chitogo_DataBase/app/models/place.py` (add three columns)
- `backend/Chitogo_DataBase/app/schemas/place.py` (expose new fields in
  `PlaceDetail` / `PlaceListItem`)
- `backend/Chitogo_DataBase/app/schemas/retrieval.py` (new fields,
  `vibe_tag` param, new sort enum values)
- `backend/Chitogo_DataBase/app/routers/places.py` (search + recommend
  signatures)
- `backend/Chitogo_DataBase/app/services/place_search.py` (vibe-tag
  filter, new sorts)
- `backend/Chat_Agent/app/tools/models.py` (`ToolPlace` new optional
  fields)
- `backend/Chat_Agent/app/tools/place_adapter.py` (`_normalize_place`
  passthrough, `search_places` accepts `vibe_tags`, new sorts)
- `backend/Chitogo_DataBase/CLAUDE.md` (recent changes block)
- `backend/Chat_Agent/CLAUDE.md` (recent changes block)
