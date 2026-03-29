# Data Model: Taipei AI Itinerary Planner

**Branch**: `001-taipei-itinerary-planner` | **Date**: 2026-03-29

---

## Entities

### 1. Venue

The core data unit. Stored in SQLite (`venues` table), bootstrapped from `backend/app/data/venues.json`.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | string | PK, e.g. `"venue_001"` | Stable identifier |
| `name` | string | NOT NULL | English venue name |
| `district` | string | NOT NULL, see District enum | Taipei district |
| `address` | string | optional | Street address |
| `category` | string | NOT NULL, see Category enum | Primary type |
| `tags` | string[] | 3–5 items | Interest tags for scoring |
| `lat` | float | NOT NULL | WGS-84 latitude |
| `lon` | float | NOT NULL | WGS-84 longitude |
| `indoor` | boolean | NOT NULL | True = primarily indoor |
| `cost_level` | integer | 1, 2, or 3 | 1=cheap, 2=mid, 3=upscale |
| `avg_dwell_minutes` | integer | > 0 | Typical visit duration |
| `trend_score` | float | 0.0–1.0 | Recency/popularity signal |
| `description` | string | optional | 1–2 sentence blurb |
| `open_hours_start` | string | "HH:MM" 24h | Opening time |
| `open_hours_end` | string | "HH:MM" 24h | Closing time |

**District enum**: `daan`, `zhongzheng`, `wanhua`, `zhongshan`, `xinyi`, `shilin`, `beitou`, `songshan`

**Category enum**: `cafe`, `restaurant`, `museum`, `gallery`, `market`, `shopping`, `park`, `temple`, `heritage`, `nightlife`, `activity`

**Tag vocabulary** (non-exhaustive): `food`, `cafes`, `art`, `history`, `shopping`, `nature`, `nightlife`, `family`, `instagrammable`, `local`, `trendy`, `quiet`, `budget-friendly`, `upscale`

---

### 2. UserPreferences (Request)

Submitted per session. Validated by Pydantic on the API boundary.

| Field | Type | Default | Validation |
|-------|------|---------|-----------|
| `district` | string | `"daan"` | Must be valid District enum value |
| `start_time` | string | `"10:00"` | "HH:MM" 24h format |
| `end_time` | string | `"14:00"` | "HH:MM", must be > start_time |
| `interests` | string[] | `["food", "cafes"]` | 1–5 items from tag vocabulary |
| `budget` | string | `"mid"` | One of: `budget`, `mid`, `splurge` |
| `companion` | string | `"solo"` | One of: `solo`, `couple`, `family`, `friends` |
| `indoor_pref` | string | `"no_preference"` | One of: `indoor`, `outdoor`, `no_preference` |

**Derived validation**:
- `end_time - start_time >= 60 minutes` → otherwise return HTTP 400 `time_range_too_short`
- `len(interests) >= 1` → otherwise apply uniform interest scoring

---

### 3. WeatherContext (Internal)

Produced by `WeatherService`. Never persisted; computed per request (with in-memory cache).

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `condition` | string | No | One of: `clear`, `cloudy`, `rain`, `drizzle`, `thunderstorm`, `snow`, `unknown` |
| `temperature_c` | float | Yes | Current temperature in Celsius |
| `precipitation_pct` | integer | Yes | Precipitation probability 0–100 |
| `icon` | string | Yes | Icon key for UI (maps to SVG/emoji) |
| `fetched_at` | datetime | No | Cache timestamp (UTC) |

**Condition mapping from OpenWeatherMap `weather[0].main`**:
- `Clear` → `clear`
- `Clouds` → `cloudy`
- `Rain`, `Drizzle` → `rain`
- `Thunderstorm` → `thunderstorm`
- `Snow` → `snow`
- Anything else / error → `unknown`

---

### 4. ScoredVenue (Internal)

Intermediate object from the scoring step. Not exposed to the client.

| Field | Type | Description |
|-------|------|-------------|
| `venue` | Venue | The underlying venue |
| `score` | float | Composite score 0.0–1.0 |
| `interest_component` | float | Scoring breakdown (debug) |
| `weather_component` | float | Scoring breakdown (debug) |
| `trend_component` | float | Scoring breakdown (debug) |
| `budget_component` | float | Scoring breakdown (debug) |

---

### 5. ItineraryStop (Internal → Response)

Represents one stop in the final ordered route. Fields are a superset of Venue.

| Field | Type | Description |
|-------|------|-------------|
| `order` | integer | 1-based position in itinerary |
| `venue_id` | string | Reference to Venue.id |
| `name` | string | Venue name |
| `category` | string | Venue category |
| `address` | string | optional |
| `lat` | float | Coordinates |
| `lon` | float | Coordinates |
| `indoor` | boolean | Indoor flag |
| `cost_level` | integer | 1–3 |
| `tags` | string[] | Interest tags |
| `arrival_time` | string | "HH:MM" — computed from route |
| `dwell_minutes` | integer | Expected time at this stop |
| `travel_to_next_minutes` | integer | Walking time to next stop (0 for last stop) |
| `reason` | string | 1–2 sentence personalized explanation |

---

### 6. ItineraryResponse (API Response)

Root response object returned by `POST /api/v1/itinerary`.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `itinerary_id` | string | No | UUID v4, for client-side tracking |
| `generated_at` | string | No | ISO-8601 UTC timestamp |
| `weather` | WeatherContext | Yes | Null when weather API unavailable |
| `stops` | ItineraryStop[] | No | Ordered list, 3–5 items |
| `total_stops` | integer | No | Length of stops array |
| `total_duration_minutes` | integer | No | From first arrival to last departure |
| `metadata` | object | Yes | Optional debug/fallback info (e.g., `{"weather_fallback": true}`) |

---

## SQLite Schema

```sql
CREATE TABLE venues (
  id                  TEXT PRIMARY KEY,
  name                TEXT NOT NULL,
  district            TEXT NOT NULL,
  address             TEXT,
  category            TEXT NOT NULL,
  tags                TEXT NOT NULL,        -- JSON array stored as string
  lat                 REAL NOT NULL,
  lon                 REAL NOT NULL,
  indoor              INTEGER NOT NULL,     -- 0 or 1
  cost_level          INTEGER NOT NULL,     -- 1, 2, or 3
  avg_dwell_minutes   INTEGER NOT NULL,
  trend_score         REAL NOT NULL DEFAULT 0.5,
  description         TEXT,
  open_hours_start    TEXT NOT NULL DEFAULT '09:00',
  open_hours_end      TEXT NOT NULL DEFAULT '22:00'
);

CREATE TABLE enrichment_cache (
  venue_id            TEXT PRIMARY KEY REFERENCES venues(id),
  trend_score         REAL NOT NULL,
  source              TEXT,                 -- e.g., "crawler_v1"
  updated_at          TEXT NOT NULL         -- ISO-8601 UTC
);
```

---

## venues.json Seed Format

```json
[
  {
    "id": "venue_001",
    "name": "Yongkang Street Café District",
    "district": "daan",
    "address": "Yongkang St, Da'an District",
    "category": "cafe",
    "tags": ["cafes", "food", "local", "instagrammable"],
    "lat": 25.0330,
    "lon": 121.5322,
    "indoor": true,
    "cost_level": 2,
    "avg_dwell_minutes": 60,
    "trend_score": 0.75,
    "description": "A charming pedestrian street lined with independent cafés and Japanese restaurants.",
    "open_hours_start": "09:00",
    "open_hours_end": "22:00"
  }
]
```

---

## State Transitions

The itinerary generation pipeline is stateless per request. The only mutable state is:

1. **SQLite venues table** — seeded once on startup; read-only during request handling
2. **Weather cache (in-memory dict)** — written by `WeatherService`; read by `ScoringEngine`
3. **Enrichment cache (SQLite)** — written by the optional crawler module (background); read by `ScoringEngine`

No per-user or per-session state is stored.

---

## Validation Rules

| Rule | Where Enforced |
|------|---------------|
| `end_time - start_time >= 60 min` | Pydantic validator on `UserPreferences` |
| `district` must be valid enum value | Pydantic `Literal` type |
| `interests` must have 1–5 items | Pydantic `min_items=1, max_items=5` |
| `trend_score` must be 0.0–1.0 | SQLite CHECK constraint + Pydantic `ge=0, le=1` |
| Response always has 3–5 stops | Asserted in `ItineraryBuilder`; fallback relaxes filters if needed |
