# Research: Place Data Service

**Feature**: 001-place-data-service
**Date**: 2026-04-16
**Phase**: 0 — Outline & Research

---

## 1. SQLAlchemy JSONB columns on PostgreSQL

**Decision**: Use `sqlalchemy.dialects.postgresql.JSONB` for all variable-structure or nested fields (`types_json`, `opening_hours_json`, `raw_json`, `feature_json`).

**Rationale**: JSONB is stored in a decomposed binary format in PostgreSQL 12+, supports indexing via GIN, and is queryable via the `->` / `->>` operators. SQLAlchemy exposes it as a first-class type through `sqlalchemy.dialects.postgresql.JSONB`, which stores Python dicts/lists and round-trips them correctly via psycopg2.

**Alternatives considered**:
- `Text` with manual `json.dumps/loads` — rejected: bypasses ORM type handling, requires manual serialization at every call site.
- `JSON` (not JSONB) — rejected: stored as text, slower to query, no GIN index support.

---

## 2. Upsert strategy by google_place_id

**Decision**: Use a query-then-update pattern for the places table upsert (check by `google_place_id`, update existing or insert new). For production scale, migrate to `sqlalchemy.dialects.postgresql.insert().on_conflict_do_update()`.

**Rationale**: The query-then-update pattern is readable, debuggable, and idiomatic for SQLAlchemy ORM. It returns the ORM object directly (including its `id`) without needing `RETURNING` clause handling, which simplifies downstream raw-source and feature writes in the same transaction. For a local-dev milestone, correctness and clarity outweigh throughput.

**Rationale for noting the pg_insert path**: `pg_insert(Place).values(...).on_conflict_do_update(...).returning(Place.id)` is the performant production path. It avoids a SELECT before every INSERT. Should be adopted if ingestion volume increases.

**Alternatives considered**:
- `session.merge()` — rejected: merges by primary key, not by `google_place_id`, so it cannot detect duplicates on the unique constraint.
- Raw SQL `INSERT ... ON CONFLICT DO UPDATE` — rejected: bypasses ORM and loses type mapping.

---

## 3. pydantic-settings configuration

**Decision**: Use `pydantic-settings` (`BaseSettings`) for `DATABASE_URL`. Read from environment variable with `.env` file fallback.

**Rationale**: `pydantic-settings` is the standard config management library for FastAPI projects. It handles environment variable binding, type coercion, and `.env` file loading with zero boilerplate. The `DATABASE_URL` default value bakes in the local dev connection string so the service works out of the box without a `.env` file.

**Default value**: `postgresql://chitogo_user:kawairoha@localhost:5432/chitogo`

**Alternatives considered**:
- `python-dotenv` directly — rejected: no type coercion or Pydantic validation; less integrated with FastAPI dependency injection.
- Hardcoded connection string — rejected: not overridable without code changes.

---

## 4. FastAPI session dependency pattern

**Decision**: Use `get_db()` as a FastAPI `Depends()` generator that yields a `SessionLocal()` instance and closes it in `finally`.

**Rationale**: This is the canonical FastAPI + SQLAlchemy pattern. It ensures sessions are always closed even on exceptions, keeps session lifetime scoped to a single request, and works seamlessly with FastAPI's dependency injection system.

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 5. Table bootstrap strategy

**Decision**: Call `Base.metadata.create_all(bind=engine)` inside a FastAPI `lifespan` context manager on startup, guarded by `checkfirst=True` (the default). Do not implement Alembic for this milestone.

**Rationale**: `create_all` is safe to call repeatedly — it skips tables that already exist. For local development this is sufficient. All models must be imported before `create_all` is called so SQLAlchemy's metadata registry is populated.

**Migration-readiness constraint**: All models use standard SQLAlchemy column types and no raw SQL DDL. When Alembic is added later, `alembic revision --autogenerate` will be able to introspect them without manual schema descriptions.

**Alternatives considered**:
- Alembic from day one — deferred: adds infrastructure overhead not justified for the local-dev milestone.
- Manual `CREATE TABLE` SQL in seed script — rejected: duplicates schema definition and drifts from ORM models.

---

## 6. place_features primary key design

**Decision**: Use `place_id` as the primary key of `place_features` (one-to-one with `places`). No separate `id` column.

**Rationale**: Feature scores are a single record per place. Using `place_id` as the PK enforces the one-to-one constraint at the database level, eliminates a separate auto-increment sequence, and makes the relationship unambiguous. Lookups always go through `place_id`.

**Alternatives considered**:
- Separate `id` + unique constraint on `place_id` — rejected: unnecessary indirection for a strict one-to-one relationship.
- Embedding scores into the `places` table — rejected: violates the governing principle (place_features is for downstream ranking scores only, kept separate to avoid polluting the main place record).

---

## 7. place_source_google retention strategy

**Decision**: Every ingestion call appends a new row to `place_source_google`. The table is append-only — old rows are never deleted or overwritten.

**Rationale**: Raw payload retention is required for debugging and future remapping (clarification #9). Appending on every ingest preserves a full history of how Google's data for a given place changed over time, enabling reprocessing with updated mapping logic.

**Implication**: `place_source_google` will grow over time. For the current milestone this is acceptable. Retention policy (e.g., keep last N per google_place_id) is deferred to production planning.

---

## 8. normalized_name derivation

**Decision**: Set `normalized_name` to `display_name.lower().strip()` at ingest time, with Unicode normalization (NFKC).

**Rationale**: Provides a consistent, case-insensitive, whitespace-trimmed form for future fuzzy matching or deduplication. NFKC normalization handles full-width characters common in Japanese place names.

**Alternatives considered**:
- Storing raw display_name only — rejected: future deduplication becomes harder without a canonical form.
- Full transliteration (e.g., romaji) — deferred: out of scope for this milestone.

---

## 9. Field mapping from Google Places API v1 shape

**Decision**: The ingestion service maps from the Google Places API (New) response shape as the initial supported source. Field paths used:

| Internal field | Google Places (New) path |
|---|---|
| google_place_id | `id` |
| display_name | `displayName.text` |
| primary_type | `primaryType` |
| types_json | `types` |
| formatted_address | `formattedAddress` |
| latitude | `location.latitude` |
| longitude | `location.longitude` |
| rating | `rating` |
| user_rating_count | `userRatingCount` |
| price_level | `priceLevel` (string like "PRICE_LEVEL_MODERATE") |
| business_status | `businessStatus` |
| google_maps_uri | `googleMapsUri` |
| website_uri | `websiteUri` |
| national_phone_number | `nationalPhoneNumber` |
| opening_hours_json | `regularOpeningHours` |

All lookups use `.get()` with `None` defaults. Nested lookups (e.g., `displayName.text`) use safe chaining. The internal schema does not mirror Google's naming — internal names are domain-defined (FR-011).

**district, indoor, outdoor, budget_level**: These are derived/normalized fields not directly present in Google's payload. For this milestone, `district` is extracted from `addressComponents` (type `sublocality` or `locality`), and `indoor`/`outdoor`/`budget_level` default to `None` at ingest time, to be enriched later.

---

## 10. Testing approach

**Decision**: pytest with a test database or mocked SQLAlchemy session for unit tests. No test infrastructure is in scope for this planning milestone — the seed script and manual `curl` commands serve as the verification path.

**Rationale**: The milestone goal is local development correctness. A test suite can be added in a follow-up task. The seed script exercises the full ingest → store → retrieve path.
