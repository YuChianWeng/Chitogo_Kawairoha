# Data Model: LLM-friendly Place Retrieval APIs

**Feature**: `002-llm-place-retrieval-apis`
**Date**: 2026-04-18

---

## Schema Changes

### 1. Add `internal_category` column to `places`

```sql
ALTER TABLE places
  ADD COLUMN internal_category VARCHAR(32)
  DEFAULT 'other';

CREATE INDEX ix_places_internal_category ON places (internal_category);
```

Applied via `scripts/migrate_add_internal_category.py` (not Alembic — deferred per project constraint).

**ORM change** (`app/models/place.py`):
```python
internal_category = Column(String(32), nullable=True, index=True)
```

---

## No New Tables

This feature adds no new tables. All new endpoints read from the existing `places` and `place_features` tables.

---

## internal_category Mapping

### Allowed values

| Value | Description |
|---|---|
| `attraction` | Tourist sites, museums, parks, galleries |
| `food` | Restaurants, cafes, bakeries, bars with food |
| `shopping` | Malls, markets, stores |
| `lodging` | Hotels, hostels, inns |
| `transport` | Stations, parking, transit hubs |
| `nightlife` | Bars, pubs, nightlife venues (non-food primary) |
| `other` | Fallback for unmapped types |

### Mapping rules

Priority order: first matching rule wins.

```python
CATEGORY_MAP = {
    # transport first — subway/train/bus are unambiguous
    "subway_station": "transport",
    "train_station": "transport",
    "bus_station": "transport",
    "bus_stop": "transport",
    "parking": "transport",
    "parking_lot": "transport",
    "parking_garage": "transport",
    "transit_station": "transport",
    # lodging
    "hotel": "lodging",
    "lodging": "lodging",
    "hostel": "lodging",
    "inn": "lodging",
    "motel": "lodging",
    # shopping
    "shopping_mall": "shopping",
    "market": "shopping",
    "store": "shopping",
    "department_store": "shopping",
    "book_store": "shopping",
    "clothing_store": "shopping",
    "convenience_store": "shopping",
    "supermarket": "shopping",
    "electronics_store": "shopping",
    "jewelry_store": "shopping",
    # nightlife (before food — bar is nightlife, not food)
    "bar": "nightlife",
    "pub": "nightlife",
    "night_club": "nightlife",
    # food
    "restaurant": "food",
    "cafe": "food",
    "coffee_shop": "food",
    "bakery": "food",
    "dessert_shop": "food",
    "ice_cream_shop": "food",
    "food_court": "food",
    "fast_food_restaurant": "food",
    "pizza_restaurant": "food",
    "sushi_restaurant": "food",
    "ramen_restaurant": "food",
    "breakfast_restaurant": "food",
    "brunch_restaurant": "food",
    "buffet_restaurant": "food",
    "seafood_restaurant": "food",
    "steak_house": "food",
    "vegetarian_restaurant": "food",
    "tea_house": "food",
    # attraction (broadest — last before other)
    "tourist_attraction": "attraction",
    "museum": "attraction",
    "park": "attraction",
    "art_gallery": "attraction",
    "zoo": "attraction",
    "aquarium": "attraction",
    "amusement_park": "attraction",
    "botanical_garden": "attraction",
    "historical_landmark": "attraction",
    "temple": "attraction",
    "shrine": "attraction",
    "church": "attraction",
    "scenic_viewpoint": "attraction",
    "hot_spring": "attraction",
    "cultural_center": "attraction",
    "point_of_interest": "attraction",
}
```

### Fallback logic

**`internal_category` is always non-null.** The mapping always produces a value.

Priority order (first match wins):
1. `primary_type` — if present and in `CATEGORY_MAP`, use it.
2. `types_json` — iterate in list order; return first match found in `CATEGORY_MAP`.
3. Fallback — return `"other"`.

```python
def map_category(primary_type: str | None, types_json: list | None) -> str:
    if primary_type and primary_type in CATEGORY_MAP:
        return CATEGORY_MAP[primary_type]
    for t in (types_json or []):
        if t in CATEGORY_MAP:
            return CATEGORY_MAP[t]
    return "other"
```

The migration backfill and ingestion both call this function, so no `places` row will ever have `internal_category IS NULL` after migration completes.

---

## budget_level Numeric Rank

Used for `max_budget_level` filter. Not stored — derived in query layer.

| String value | Numeric rank |
|---|---|
| `PRICE_LEVEL_FREE` | 0 |
| `INEXPENSIVE` | 1 |
| `MODERATE` | 2 |
| `EXPENSIVE` | 3 |
| `VERY_EXPENSIVE` | 4 |
| `null` | excluded when filter is active |

Filter semantics: `max_budget_level=2` returns places where rank ≤ 2 (FREE, INEXPENSIVE, MODERATE).

```python
BUDGET_RANK = {
    "PRICE_LEVEL_FREE": 0,
    "INEXPENSIVE": 1,
    "MODERATE": 2,
    "EXPENSIVE": 3,
    "VERY_EXPENSIVE": 4,
}
```

---

## Haversine Distance Formula (SQL)

Used in `GET /places/nearby`. Implemented as a raw SQL expression — no PostGIS required.

**Hard limit**: `radius_m` must be between 1 and **10000** (10 km). Requests exceeding this → HTTP 422. Rationale: Taipei city radius is ~10 km; larger values cause poor query performance and semantically meaningless results for POI use cases.

```sql
(
  6371000 * acos(
    cos(radians(:lat)) * cos(radians(latitude)) *
    cos(radians(longitude) - radians(:lng)) +
    sin(radians(:lat)) * sin(radians(latitude))
  )
) AS distance_m
```

Bounding box pre-filter applied before Haversine to limit rows scanned:

```python
lat_delta = radius_m / 111_320  # degrees per meter (approx)
lng_delta = radius_m / (111_320 * cos(radians(lat)))
```

---

## open_now Evaluation

The `opening_hours_json` column stores a Google Places `regularOpeningHours` object.

`opening_hours_json` uses `regularOpeningHours` as the primary source for `open_now` evaluation.
`currentOpeningHours` is not used in Phase 1.

```json
{
  "periods": [
    {"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 21, "minute": 0}},
    ...
  ]
}
```

`open_now` is evaluated in Python at query time using the server's local timezone (Asia/Taipei). Places where `opening_hours_json` is null or lacks a `periods` key are **excluded** when `open_now=true`.

---

## Recommendation Default Category Behavior

When `POST /places/recommend` is called **without** `internal_category`:

Default filter is applied: only places in `["attraction", "food", "shopping", "lodging"]` are included.

This prevents transport hubs, parking, and low-value POIs from dominating results when the LLM has no category preference.

Document this default clearly in API response so callers can override by passing `internal_category` explicitly.

---

## Recommendation Ranking

When `PlaceFeatures` are present, a weighted score is computed:

```python
score = mean([
    couple_score, family_score, food_score, culture_score,
    rainy_day_score, crowd_score, transport_score, hidden_gem_score
])  # only include non-null values
```

Sort: `score DESC`, then `rating DESC` as tiebreaker.

When no feature scores exist: sort by `rating DESC`.
