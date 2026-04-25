# Data Model: ChitoGO PRD State-Machine Trip Wizard

**Phase 1 output** — entities, fields, relationships, state transitions

---

## Entity Overview

```
Session ──────────────────────── (central hub)
  │
  ├── TransportConfig          (embedded, set during TRANSPORT state)
  ├── AccommodationConfig      (embedded, set during TRANSPORT state)
  ├── list[VisitedStop]        (appended on each POST /trip/rate)
  ├── CandidateCard?           (pending_venue — set on select, cleared on rate)
  ├── gene_affinity_weights    (dict[str,float] — updated per rating)
  └── ReachableCache?          (TTL=5 min, keyed by origin coords)

TravelGene ─────────────────────── (static config, not stored in DB)
  └── base_affinity_weights    (dict[str,float] — category → weight)

Hotel (LegalLodging) ───────────── (PostgreSQL in Data Service — existing model)
  └── used by PlaceToolAdapter.check_lodging_legal_status()

Place / Venue ──────────────────── (PostgreSQL in Data Service — existing model)
  └── used by PlaceToolAdapter.search_places(), nearby_places()

CandidateCard ──────────────────── (computed, transient — stored in session as pending_venue)
JourneySummary ─────────────────── (computed on-demand from session.visited_stops)
```

---

## Session (extended)

**Location**: `backend/Chat_Agent/app/session/models.py`

New fields added to the existing `Session` model (all optional with defaults for backward compatibility):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `flow_state` | `FlowState` | `QUIZ` | Current FSM state |
| `quiz_answers` | `dict[str, str]` | `{}` | Q1–Q9 → "A"/"B"/"C" |
| `travel_gene` | `str \| None` | `None` | Resolved gene name (set after quiz) |
| `mascot` | `str \| None` | `None` | Mascot identifier (set after quiz) |
| `accommodation` | `AccommodationConfig \| None` | `None` | Set during TRANSPORT state |
| `return_time` | `str \| None` | `None` | HH:MM optional return target |
| `return_destination` | `str \| None` | `None` | "hotel" or transit station name |
| `transport_config` | `TransportConfig \| None` | `None` | Set during TRANSPORT state |
| `visited_stops` | `list[VisitedStop]` | `[]` | Appended per completed visit |
| `gene_affinity_weights` | `dict[str, float]` | `{}` | Live-adjusted affinity per category |
| `go_home_reminded_at` | `datetime \| None` | `None` | Throttle: last reminder fire time |
| `pending_venue` | `CandidateCard \| None` | `None` | Venue selected; awaiting "我到了！" |
| `reachable_cache` | `ReachableCache \| None` | `None` | 5-min TTL reachable venue ID list |

**Validation rules**:
- `flow_state` transitions are enforced by `SessionFSM.assert_state()` before every trip endpoint; raises `ValueError("state_error:expected_{STATE}")` on violation
- `quiz_answers` must contain keys Q1–Q9 before gene classification
- `return_time` must match `HH:MM` pattern (reuse existing `_TIME_PATTERN`)

---

## FlowState

**Location**: `backend/Chat_Agent/app/session/models.py` (new enum)

```python
class FlowState(str, Enum):
    QUIZ = "QUIZ"
    TRANSPORT = "TRANSPORT"
    RECOMMENDING = "RECOMMENDING"
    RATING = "RATING"       # sub-state: venue selected, awaiting arrival confirmation
    ENDED = "ENDED"
```

**Transition table**:

| From | Event | To |
|------|-------|-----|
| QUIZ | quiz submitted successfully | TRANSPORT |
| TRANSPORT | setup submitted successfully | RECOMMENDING |
| RECOMMENDING | POST /trip/select called | RATING |
| RATING | POST /trip/rate called | RECOMMENDING |
| RECOMMENDING | "我想回家" → GET /trip/summary | ENDED |
| RATING | "我想回家" → GET /trip/summary | ENDED |

---

## AccommodationConfig

**Location**: `backend/Chat_Agent/app/session/models.py` (new model)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `booked` | `bool` | yes | True = has specific hotel booking |
| `hotel_name` | `str \| None` | if booked | User-entered hotel name |
| `hotel_lat` | `float \| None` | set by validator | Resolved coordinates |
| `hotel_lng` | `float \| None` | set by validator | Resolved coordinates |
| `hotel_valid` | `bool \| None` | set by validator | Legal registry check result |
| `matched_name` | `str \| None` | set by validator | Canonical hotel name |
| `district` | `str \| None` | if not booked | Preferred district |
| `budget_tier` | `str \| None` | if not booked | "budget"/"mid"/"luxury" |

---

## TransportConfig

**Location**: `backend/Chat_Agent/app/session/models.py` (new model)

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `modes` | `list[str]` | non-empty; values in {"walk","transit","drive"} | Enabled transport modes |
| `max_minutes_per_leg` | `int` | 1–120 | Max travel time per leg |

---

## VisitedStop

**Location**: `backend/Chat_Agent/app/session/models.py` (new model)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `venue_id` | `str \| int` | yes | Venue identifier from Data Service |
| `venue_name` | `str` | yes | Display name |
| `category` | `str` | yes | "restaurant" or "attraction" |
| `primary_type` | `str \| None` | no | e.g., "cafe", "museum" |
| `address` | `str \| None` | no | Formatted address |
| `lat` | `float` | yes | Venue coordinates |
| `lng` | `float` | yes | Venue coordinates |
| `arrived_at` | `datetime` | yes | UTC timestamp of "我到了！" |
| `star_rating` | `int` | 1–5 | User rating |
| `tags` | `list[str]` | default `[]` | Optional quick-tag metadata |

---

## CandidateCard

**Location**: `backend/Chat_Agent/app/session/models.py` (new model; also returned in API responses)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `venue_id` | `str \| int` | yes | Venue identifier |
| `name` | `str` | yes | Display name |
| `category` | `str` | yes | "restaurant" or "attraction" |
| `primary_type` | `str \| None` | no | Type tag from Data Service |
| `address` | `str \| None` | no | Formatted address |
| `lat` | `float` | yes | Coordinates |
| `lng` | `float` | yes | Coordinates |
| `rating` | `float \| None` | no | Base star rating (1–5 scale) |
| `distance_min` | `int` | yes | Estimated travel time in minutes |
| `why_recommended` | `str` | yes | LLM-generated one-sentence reason |
| `partial` | `bool` | default `False` | True if 3+3 split not achievable |

---

## ReachableCache

**Location**: `backend/Chat_Agent/app/session/models.py` (new model)

| Field | Type | Description |
|-------|------|-------------|
| `origin_lat` | `float` | Cache key: origin latitude |
| `origin_lng` | `float` | Cache key: origin longitude |
| `venue_ids` | `list[str \| int]` | Reachable venue IDs |
| `expires_at` | `datetime` | UTC expiry (5 min from creation) |

Cache is invalidated when origin changes by >100 m (haversine check) or TTL expires.

---

## TravelGene (static config)

**Location**: `backend/Chat_Agent/app/orchestration/gene_classifier.py` (module-level constant)

Not stored in the database — defined as a Python dict. Loaded once at import time.

| Gene | Mascot ID | Base category affinities (key examples) |
|------|-----------|----------------------------------------|
| 文清 | wenqing_cat | cafe: 1.5, bookstore: 1.5, museum: 1.3 |
| 親子 | family_bear | park: 1.4, museum: 1.3, aquarium: 1.5 |
| 不常來 | tourist_owl | landmark: 1.5, market: 1.4, temple: 1.4 |
| 夜貓子 | night_fox | bar: 1.5, nightmarket: 1.5, club: 1.4 |
| 一日 | daytrip_rabbit | market: 1.3, park: 1.2, landmark: 1.2 |
| 野外 | outdoor_deer | park: 1.5, trail: 1.5, mountain: 1.5 |

---

## JourneySummary (computed)

Not stored — derived on-demand from `session.visited_stops`.

| Field | Type | Derivation |
|-------|------|-----------|
| `stops` | `list[VisitedStop]` | `session.visited_stops` (ordered) |
| `total_stops` | `int` | `len(visited_stops)` |
| `total_elapsed_min` | `int` | `(last arrived_at − session.created_at).seconds // 60` |
| `total_distance_m` | `int` | Sum of leg distances from `visited_stops` coordinates (haversine) |
| `mascot_farewell` | `str` | LLM-generated farewell using gene + stops summary |
| `travel_gene` | `str` | `session.travel_gene` |
| `mascot` | `str` | `session.mascot` |

---

## Existing Entities (unchanged, referenced)

### Hotel / LegalLodging (Data Service PostgreSQL)
Already exists in `backend/Chitogo_DataBase/app/models/legal_lodging.py`. Fields include: `name`, `district`, `address`, `registration_number`, `category`. Accessed via `PlaceToolAdapter.check_lodging_legal_status()` and `search_lodging_candidates()`.

### Place / Venue (Data Service PostgreSQL)
Already exists in `backend/Chitogo_DataBase/app/models/place.py`. Accessed via `PlaceToolAdapter.search_places()`, `nearby_places()`, `recommend_places()`.
