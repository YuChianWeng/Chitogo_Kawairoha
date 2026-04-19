# Quickstart & Verification: LLM-friendly Place Retrieval APIs

**Feature**: `002-llm-place-retrieval-apis`
**Date**: 2026-04-18
**Prerequisite**: `001-place-data-service` running; at least one place seeded in the DB.

---

## Setup

```bash
# 1. Run migration (adds internal_category column + backfills existing rows)
python scripts/migrate_add_internal_category.py

# 2. Start service
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Verify service is healthy
curl http://localhost:8000/api/v1/health/db
# Expected: {"status":"ok","database":"connected"}
```

---

## Step 1 — Search API

```bash
# Search with no filters (returns all)
curl "http://localhost:8000/api/v1/places/search"
# Expected: {"items":[...],"total":N,"limit":20,"offset":0}

# Filter by district
curl "http://localhost:8000/api/v1/places/search?district=中正區"
# Expected: items where district == "中正區"

# Filter by internal_category
curl "http://localhost:8000/api/v1/places/search?internal_category=attraction"
# Expected: items where internal_category == "attraction"

# Filter by keyword
curl "http://localhost:8000/api/v1/places/search?keyword=華山"
# Expected: items where display_name contains "華山"

# Filter by min_rating
curl "http://localhost:8000/api/v1/places/search?min_rating=4.0"
# Expected: items where rating >= 4.0

# Invalid sort → 422
curl "http://localhost:8000/api/v1/places/search?sort=invalid"
# Expected: HTTP 422
```

---

## Step 2 — Nearby API

```bash
# Nearby 中正區 (lat=25.0441, lng=121.5292), radius 1km
curl "http://localhost:8000/api/v1/places/nearby?lat=25.0441&lng=121.5292&radius_m=1000"
# Expected: items with distance_m field; all within 1000m

# Radius too large → 422
curl "http://localhost:8000/api/v1/places/nearby?lat=25.0441&lng=121.5292&radius_m=50000"
# Expected: HTTP 422 "radius_m must not exceed 10000"

# Invalid coordinates → 422
curl "http://localhost:8000/api/v1/places/nearby?lat=999&lng=121.5292&radius_m=1000"
# Expected: HTTP 422
```

---

## Step 3 — Batch Detail

```bash
# Known place IDs
curl -X POST http://localhost:8000/api/v1/places/batch \
  -H "Content-Type: application/json" \
  -d '{"place_ids": [1]}'
# Expected: {"items":[{full detail record}]}

# Mix of valid + invalid IDs
curl -X POST http://localhost:8000/api/v1/places/batch \
  -H "Content-Type: application/json" \
  -d '{"place_ids": [1, 9999]}'
# Expected: {"items":[{record for id=1}]} — 9999 silently omitted

# All unknown
curl -X POST http://localhost:8000/api/v1/places/batch \
  -H "Content-Type: application/json" \
  -d '{"place_ids": [9999]}'
# Expected: {"items":[]}
```

---

## Step 4 — Recommend API

```bash
# Recommend food in 大安區 or 信義區
curl -X POST http://localhost:8000/api/v1/places/recommend \
  -H "Content-Type: application/json" \
  -d '{"internal_category":"food","min_rating":4.0,"limit":5}'
# Expected: {"items":[...],"total":N}

# Empty result (filters too strict)
curl -X POST http://localhost:8000/api/v1/places/recommend \
  -H "Content-Type: application/json" \
  -d '{"min_rating":5.0,"max_budget_level":0}'
# Expected: {"items":[],"total":0} — not an error
```

---

## Step 5 — Stats API

```bash
curl http://localhost:8000/api/v1/places/stats
# Expected: {"total_places":N,"by_district":{...},"by_internal_category":{...},"by_primary_type":{...}}
# Verify: sum of by_district values == total_places (for rows where district is not null)
```

---

## Step 6 — Categories API

```bash
curl http://localhost:8000/api/v1/places/categories
# Expected: {"categories":[{"value":"attraction","label":"Attraction","representative_types":[...]}, ...]}
# Verify: 7 categories returned (attraction, food, shopping, lodging, transport, nightlife, other)
```

---

## Step 7 — Backward Compatibility

```bash
# Original list endpoint must still work
curl http://localhost:8000/api/v1/places
# Expected: same response shape as before this feature

# Original detail endpoint must still work
curl http://localhost:8000/api/v1/places/1
# Expected: same response shape as before this feature
```

---

## Step 8 — internal_category populated

```bash
# Confirm internal_category is not null on seeded place
curl http://localhost:8000/api/v1/places/1 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('internal_category'))"
# Expected: "attraction" (or another non-null value)
```
