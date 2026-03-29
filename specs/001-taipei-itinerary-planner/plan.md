# Implementation Plan: Taipei AI Itinerary Planner

**Branch**: `001-taipei-itinerary-planner` | **Date**: 2026-03-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-taipei-itinerary-planner/spec.md`

## Summary

Build an AI-powered same-day Taipei itinerary planner for the YTP hackathon. Users submit preferences (district, time range, interests, budget, companion type, indoor/outdoor) and receive a 3–5 stop itinerary with suggested arrival times and personalized reasons, adjusted for live weather. The backend is FastAPI with a rule-based scoring engine over a curated seed venue dataset; the frontend is Vue 3. LLM usage is optional and limited to explanation generation only.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x / Node 20 (frontend)
**Primary Dependencies**: FastAPI 0.111, Pydantic v2, aiosqlite, Vue 3 + Vite 5, Axios, OpenWeatherMap API
**Storage**: SQLite for venue data and optional enrichment cache; seed data bootstrapped from `venues.json`
**Testing**: pytest + httpx (backend), Vitest (frontend)
**Target Platform**: Linux/macOS server (hackathon demo); browser (Chrome/Safari desktop + mobile)
**Project Type**: web-service (FastAPI) + web-application (Vue 3 SPA)
**Performance Goals**: Full itinerary response in under 10 seconds end-to-end; weather fetch cached for 30 minutes
**Constraints**: No user auth for MVP; single-session stateless; graceful degradation if weather API unavailable
**Scale/Scope**: Hackathon demo — single server, ~80 curated venues, up to 50 concurrent users

---

## Constitution Check

The project constitution file contains placeholder text only (no project-specific principles have been ratified). No violations to evaluate.

**Gate: PASSED** — Proceeding to Phase 0.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-taipei-itinerary-planner/
├── plan.md              # This file
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity schemas
├── quickstart.md        # Phase 1: local dev setup
├── contracts/
│   └── api.md           # REST API contract
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py                    # FastAPI app factory, CORS, startup hooks
│   ├── api/
│   │   └── v1/
│   │       ├── router.py          # Mounts all v1 routes
│   │       └── itinerary.py       # POST /api/v1/itinerary
│   ├── services/
│   │   ├── weather.py             # WeatherService: fetch + cache + fallback
│   │   ├── scoring.py             # ScoringEngine: rule-based venue ranking
│   │   ├── routing.py             # RouteOptimizer: nearest-neighbor ordering
│   │   └── itinerary_builder.py   # ItineraryBuilder: assemble final output
│   ├── models/
│   │   ├── schemas.py             # Pydantic request/response models
│   │   └── db.py                  # SQLite venue table, aiosqlite helpers
│   ├── data/
│   │   └── venues.json            # Seed dataset (~80 venues across districts)
│   └── config.py                  # Settings via pydantic-settings / .env
├── tests/
│   ├── test_scoring.py
│   ├── test_weather.py
│   └── test_api.py
├── requirements.txt
├── requirements-dev.txt
└── .env.example

frontend/
├── src/
│   ├── components/
│   │   ├── PreferenceForm.vue     # 6-field input form with defaults
│   │   ├── ItineraryDisplay.vue   # Ordered list of stop cards
│   │   ├── StopCard.vue           # Single stop: name, time, reason, tag
│   │   └── WeatherBadge.vue       # Condition icon + temperature
│   ├── pages/
│   │   └── HomePage.vue           # Root page: form + output
│   ├── services/
│   │   └── api.ts                 # Typed Axios wrapper for /api/v1/itinerary
│   └── types/
│       └── itinerary.ts           # TypeScript interfaces matching API contract
├── public/
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

**Structure Decision**: Web-application layout. Backend and frontend are separate top-level directories. Both are started independently (`uvicorn` + `vite dev`) or together via a root `Makefile`.

---

## Architecture Overview

```
Browser (Vue 3 SPA)
    │  POST /api/v1/itinerary  (JSON preferences)
    ▼
FastAPI  ─────────────────────────────────────────────────────────
    │
    ├── WeatherService
    │     ├─ GET OpenWeatherMap /weather?q=Taipei,TW
    │     ├─ In-memory TTL cache (30 min)
    │     └─ Fallback: WeatherContext(condition="unknown", modifier=neutral)
    │
    ├── VenueRepository
    │     ├─ Seed venues.json → SQLite on startup
    │     ├─ filter(district, time_budget, indoor_pref, budget)
    │     └─ Returns: List[Venue]
    │
    ├── ScoringEngine
    │     ├─ score = interest(40%) + weather(30%) + trend(20%) + budget(10%)
    │     └─ Returns: List[ScoredVenue] sorted descending
    │
    ├── RouteOptimizer
    │     ├─ Greedy nearest-neighbor from top-scored anchor
    │     ├─ Applies time budget constraint
    │     └─ Returns: ordered List[ItineraryStop] (3–5 stops)
    │
    └── ItineraryBuilder
          ├─ Assign arrival times, travel_to_next_minutes
          ├─ Generate reason string (template or optional LLM)
          └─ Returns: ItineraryResponse
```

---

## Module Boundaries

| Module | Responsibility | Inputs | Outputs |
|--------|---------------|--------|---------|
| `api/v1/itinerary.py` | HTTP boundary: validate, orchestrate, respond | HTTP request | HTTP response JSON |
| `services/weather.py` | Fetch + cache weather; map to WeatherContext | district string | WeatherContext |
| `services/scoring.py` | Stateless venue ranking | List[Venue], UserPreferences, WeatherContext | List[ScoredVenue] |
| `services/routing.py` | Greedy route ordering with time budget | List[ScoredVenue], start_time, end_time | List[ItineraryStop] |
| `services/itinerary_builder.py` | Final assembly: timing + reasons | List[ItineraryStop], WeatherContext | ItineraryResponse |
| `models/db.py` | SQLite access; venue CRUD; seed loader | venues.json path | List[Venue] |
| `models/schemas.py` | All Pydantic request/response types | — | type definitions |

Modules communicate through typed Pydantic/dataclass objects only — no global mutable state.

---

## Recommendation Pipeline

### Step 1 — Filter

```
candidates = venues where:
  venue.district == prefs.district
    OR haversine_km(venue, district_center) <= 3.0
  AND venue.cost_level in allowed_levels(prefs.budget)
  AND (prefs.indoor_pref == "no_preference"
       OR venue.indoor == (prefs.indoor_pref == "indoor"))
  AND venue.open_hours covers [prefs.start_time, prefs.end_time]
```

### Step 2 — Score

```
score(v) =
  interest_score(v, prefs) * 0.40
  + weather_score(v, weather) * 0.30
  + v.trend_score             * 0.20
  + budget_score(v, prefs)    * 0.10

interest_score  = len(intersection(prefs.interests, v.tags)) / max(len(prefs.interests), 1)
                  (floor at 0.3 if category alone matches with no tag overlap)

weather_score matrix (condition x indoor flag):
  rain   + indoor  = 1.00  |  rain   + outdoor = 0.10
  cloudy + outdoor = 0.75  |  cloudy + indoor  = 0.80
  clear  + outdoor = 1.00  |  clear  + indoor  = 0.70
  unknown (fallback)        = 0.85

budget_score (cost_level: 1=cheap, 2=mid, 3=upscale):
  budget  pref: [1→1.0, 2→0.4, 3→0.0]
  mid     pref: [1→0.7, 2→1.0, 3→0.6]
  splurge pref: [1→0.4, 2→0.8, 3→1.0]
```

### Step 3 — Route (Greedy Nearest-Neighbor)

```
1. Anchor = highest-scored venue (stop 1)
2. current_pos = anchor.coords; current_time = prefs.start_time
3. remaining_candidates = sorted_pool minus anchor
4. while len(stops) < 5 and current_time < prefs.end_time:
     next = argmax over remaining of:
       score(v) * (1 / (1 + haversine_km(current_pos, v.coords)))
     travel_mins = max(5, haversine_km(current_pos, next.coords) * 12)
     if current_time + travel_mins + next.avg_dwell_minutes > prefs.end_time: break
     append stop; current_time += travel_mins + next.avg_dwell_minutes
     current_pos = next.coords
```

Travel time estimate: 12 min/km accounts for urban walking pace plus navigation buffer.

### Step 4 — Reason Generation

**MVP template** (always available):
```
"{name} is a {category} in {district}, popular with {companion} visitors and well-suited
 for {top_interest} on a {weather_condition} {time_of_day}."
```

**Optional LLM enrichment** (enabled by `USE_LLM=true` in `.env`):
- Construct prompt with venue metadata + user preferences + weather
- Budget: ≤ 2 s per stop; fall back to template on timeout or error
- Stops processed in parallel; total LLM time stays within the 10 s SLA

---

## API Design

See `contracts/api.md` for the full typed contract.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/itinerary` | Generate itinerary from preferences |
| `GET`  | `/api/v1/health` | Liveness check |
| `GET`  | `/api/v1/venues` | List venues (debug/admin, optional) |

---

## Fallback Strategy

| Failure Scenario | Fallback Behavior |
|-----------------|-------------------|
| Weather API unavailable / timeout | `WeatherContext(condition="unknown")`; neutral scores (0.85); omit weather badge |
| Fewer than 3 venues match filters | Relax district radius to 5 km; then relax indoor/outdoor preference |
| LLM timeout / unavailable | Template-based reason strings; itinerary still complete |
| No venues for selected interest | Return venues from other categories in district; note in response `metadata` |
| Time range < 60 minutes | HTTP 400 with `error_code: "time_range_too_short"` and user-facing message |
| Crawler enrichment data absent | Use seed `trend_score` values; pipeline unchanged |

---

## MVP Scope vs Future Scope

### MVP (Hackathon)

- Preference form — 6 fields, sensible defaults, client-side validation
- OpenWeatherMap integration — in-memory cache + graceful fallback
- SQLite venue database — ~80 curated venues across 8 Taipei districts
- Rule-based scoring — interest + weather + trend + budget weights
- Greedy nearest-neighbor route optimizer
- Template-based reason strings
- Card-based itinerary UI with weather badge
- Fallback on all external service failures

### Stretch Goals (Hackathon Bonus, Time Permitting)

- LLM-generated reason strings (`USE_LLM=true` toggle)
- Leaflet.js map overlay showing stop sequence
- `MOCK_WEATHER` env var to simulate rain/sun for demo reliability
- Crawler/enrichment module script for updated trend scores

### Post-Hackathon

- User accounts and saved itineraries
- Multi-day planning
- Traditional Chinese UI
- Real-time venue availability (Google Places / Foursquare)
- Export to PDF or calendar (.ics)
- User rating feedback loop to improve scoring weights over time
- Social/crawler enrichment as a primary (not optional) data source
