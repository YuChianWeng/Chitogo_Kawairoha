---
description: "Task list for Taipei AI Itinerary Planner"
---

# Tasks: Taipei AI Itinerary Planner

**Input**: Design documents from `/specs/001-taipei-itinerary-planner/`
**Branch**: `001-taipei-itinerary-planner`
**Stack**: Python 3.11 + FastAPI (backend) · Vue 3 + TypeScript (frontend) · SQLite + venues.json (data)

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (touches different files, no incomplete dependencies)
- **[Story]**: User story this task belongs to — US1 through US5
- Each task includes a **Validation** line describing the "done" signal

---

## Phase 1: Setup

**Purpose**: Create the repository skeleton so both backend and frontend developers can start working independently.

- [X] T001 Create top-level directory structure (`backend/`, `frontend/`, `Makefile`, `.gitignore`) per plan.md project layout
  - **Validation**: `ls` shows `backend/`, `frontend/`, `Makefile`; `.gitignore` excludes `*.db`, `.env`, `__pycache__`, `node_modules`

- [X] T002 [P] Initialize Python backend: create `backend/` venv, write `backend/requirements.txt` (fastapi, uvicorn, aiosqlite, pydantic-settings, httpx, python-dotenv, requests), write `backend/.env.example` with `OPENWEATHER_API_KEY`, `USE_LLM=false`, `MOCK_WEATHER=`, `DATABASE_URL`
  - **Validation**: `pip install -r backend/requirements.txt` completes with no errors; `.env.example` contains all 4 keys

- [X] T003 [P] Initialize Vue 3 + TypeScript frontend: run `npm create vite@latest frontend -- --template vue-ts` in repo root, then `npm install axios` inside `frontend/`
  - **Validation**: `cd frontend && npm run dev` starts dev server on port 5173 and renders the default Vite welcome page

- [X] T004 Configure Vite dev proxy: add `server.proxy` in `frontend/vite.config.ts` to forward `/api` → `http://localhost:8000`
  - **Validation**: With backend running, a browser `fetch('/api/v1/health')` from the Vite dev origin returns `{"status":"ok"}` without CORS errors

- [X] T005 Create FastAPI app factory with CORS in `backend/app/main.py`: instantiate `FastAPI`, add `CORSMiddleware` (allow all origins in dev), include the v1 router, add a `startup` event that seeds the DB
  - **Validation**: `uvicorn app.main:app --reload --port 8000` starts without errors; `curl http://localhost:8000/api/v1/health` returns `{"status":"ok","version":"0.1.0"}`

**Checkpoint**: Both servers start. Browser can reach `/api/v1/health` through Vite proxy. Backend and frontend work can now proceed in parallel.

---

## Phase 2: Foundation — Data Layer & Schemas

**Purpose**: Shared data contracts and the venue database — everything else depends on these.

⚠️ **CRITICAL**: No user story tasks can begin until this phase is complete.

- [X] T006 Write all Pydantic schemas in `backend/app/models/schemas.py`: `UserPreferencesRequest` (with field defaults and a `@validator` that raises 400 when `end_time - start_time < 60 min`), `WeatherContext`, `ScoredVenue`, `ItineraryStopResponse`, `ItineraryResponse`, `ErrorResponse`
  - **Validation**: `python -c "from app.models.schemas import UserPreferencesRequest; print(UserPreferencesRequest().model_dump())"` prints the default values; submitting `start_time="13:30", end_time="14:00"` raises `ValidationError`

- [X] T007 [P] Write SQLite schema + aiosqlite helpers in `backend/app/models/db.py`: `CREATE TABLE venues` and `CREATE TABLE enrichment_cache` per data-model.md, plus async functions `init_db()`, `seed_from_json(path)`, `get_venues(filters)`, `get_venue_by_id(id)`
  - **Validation**: `python -c "import asyncio; from app.models.db import init_db; asyncio.run(init_db())"` creates `taipei.db` with both tables; no SQL errors

- [X] T008 [P] Create `backend/app/data/venues.json` seed dataset: minimum 30 venues covering at least 6 districts (`daan`, `zhongzheng`, `wanhua`, `zhongshan`, `xinyi`, `shilin`), mixed `indoor`/`outdoor`, all 3 `cost_level` values, varied `category` and `tags`; include real Taipei coordinates (WGS-84)
  - **Validation**: `python -m json.tool backend/app/data/venues.json` parses without error; `jq 'length' venues.json` ≥ 30; `jq '[.[].district] | unique' venues.json` shows ≥ 6 distinct districts; each entry has all required fields from data-model.md

- [X] T009 Wire DB seed into FastAPI startup event in `backend/app/main.py`: on `startup`, call `init_db()` then `seed_from_json("app/data/venues.json")` only if `venues` table is empty
  - **Validation**: Delete `taipei.db`, restart uvicorn — table is auto-created and seeded; `GET /api/v1/venues` (once added) returns ≥ 30 rows; restarting a second time does not duplicate rows

- [X] T010 Create `backend/app/config.py` using `pydantic-settings`: `Settings` class with `OPENWEATHER_API_KEY: str = ""`, `USE_LLM: bool = False`, `MOCK_WEATHER: str = ""`, `DATABASE_URL: str = "sqlite+aiosqlite:///./taipei.db"`, `WEATHER_CACHE_TTL_MINUTES: int = 30`; export a `settings` singleton
  - **Validation**: `from app.config import settings; print(settings.USE_LLM)` prints `False`; setting `USE_LLM=true` in `.env` changes it to `True`

- [X] T011 [P] Create TypeScript types in `frontend/src/types/itinerary.ts` mirroring the API contract: `UserPreferencesRequest`, `WeatherContext`, `ItineraryStop`, `ItineraryResponse`, `ErrorResponse`
  - **Validation**: `cd frontend && npx tsc --noEmit` passes; all field names and types match `contracts/api.md` exactly

**Checkpoint**: Schemas, DB, seed data, and config are all in place. US1–US5 can now start.

---

## Phase 3: US1 — Core Itinerary Generation Pipeline (Priority: P1) 🎯 MVP

**Goal**: The full backend pipeline (filter → score → route → build) working end-to-end, returning a valid `ItineraryResponse` for a POST request. Frontend wired to show raw output.

**Independent Test**: `curl -s -X POST http://localhost:8000/api/v1/itinerary -H "Content-Type: application/json" -d '{"district":"daan"}' | python3 -m json.tool` returns a response with `total_stops` between 3 and 5, each stop having `name`, `arrival_time`, and `reason`.

### Backend

- [X] T012 [US1] Implement `VenueRepository.filter()` in `backend/app/models/db.py`: query venues by district match OR `haversine_km ≤ 3.0`, filter by `cost_level` (budget→[1], mid→[1,2], splurge→[2,3]), filter by `indoor` if `indoor_pref` is not `no_preference`, filter by `open_hours` covering `[start_time, end_time]`; return `List[Venue]`
  - **Validation**: Call `filter(district="daan", budget="mid", indoor_pref="indoor", ...)` — result contains only `indoor=True` venues in or near Da'an; call with `indoor_pref="no_preference"` — result includes both indoor and outdoor venues

- [X] T013 [P] [US1] Implement `ScoringEngine.score()` in `backend/app/services/scoring.py`: compute `interest_score` (tag overlap ratio, floor 0.3 on category match), `trend_score` (pass-through from venue), `budget_score` (lookup table per plan.md); combine as `interest*0.40 + trend*0.20 + budget*0.10` (weather component = 0.85 neutral until US4); return `List[ScoredVenue]` sorted descending
  - **Validation**: Given two venues identical except one has matching interest tags, the one with matching tags scores higher; budget=budget + cost_level=3 venue scores 0.0 on budget component

- [X] T014 [US1] Implement `RouteOptimizer.build_route()` in `backend/app/services/routing.py`: pick highest-scored venue as anchor (stop 1); greedily pick next = `argmax score(v) / (1 + haversine_km(current, v))` while `current_time + travel_mins + dwell ≤ end_time` and `len(stops) < 5`; compute `travel_mins = max(5, km * 12)`; return `List[ItineraryStop]` (order, arrival_time, travel_to_next_minutes)
  - **Validation**: Given 4-hour window with 5 candidate venues, output has 3–5 stops; stops are in chronological order; final stop has `travel_to_next_minutes = 0`; no stop's arrival_time exceeds `end_time`

- [X] T015 [US1] Implement `ItineraryBuilder.build()` in `backend/app/services/itinerary_builder.py`: fill `reason` for each stop using template `"{name} is a {category} in {district}, popular with {companion} visitors and well-suited for {top_interest} on a {weather_condition} {time_of_day}."`; assemble and return `ItineraryResponse` with UUID, timestamp, `total_stops`, `total_duration_minutes`, `metadata`
  - **Validation**: Each stop in the response has a non-empty `reason` string; `itinerary_id` is a valid UUID4; `total_duration_minutes` equals last departure − first arrival

- [X] T016 [US1] Implement `POST /api/v1/itinerary` handler in `backend/app/api/v1/itinerary.py`: validate `UserPreferencesRequest`, call `filter()` → `score()` → `build_route()` → `build()`; return `ItineraryResponse`; wire into `backend/app/api/v1/router.py`
  - **Validation**: `curl -X POST /api/v1/itinerary -d '{}'` returns 200 with default preferences; `curl` with `start_time="13:30" end_time="14:00"` returns 400 `time_range_too_short`; response time < 5 s (no weather yet)

- [X] T017 [US1] Implement `GET /api/v1/health` in `backend/app/api/v1/router.py`: return `{"status":"ok","version":"0.1.0"}`
  - **Validation**: `curl http://localhost:8000/api/v1/health` returns 200 with correct body

### Frontend

- [X] T018 [P] [US1] Implement `api.ts` Axios client in `frontend/src/services/api.ts`: export `generateItinerary(prefs: UserPreferencesRequest): Promise<ItineraryResponse>` that POSTs to `/api/v1/itinerary`; throws typed `ErrorResponse` on 4xx/5xx
  - **Validation**: Import and call in browser console — returns an `ItineraryResponse` object with correct TypeScript types; calling with invalid data surfaces a typed error

- [X] T019 [US1] Wire `HomePage.vue` in `frontend/src/pages/HomePage.vue`: add a submit button that calls `api.ts` with hardcoded default preferences and renders the raw JSON response in a `<pre>` block; show "Loading…" text while waiting
  - **Validation**: Clicking the button shows "Loading…" then renders the full JSON response; no console errors; works within 10 s

**Checkpoint**: Core backend pipeline and basic frontend wiring are complete. A working MVP exists — submitting generates a real itinerary.

---

## Phase 4: US2 — Preference Input Form (Priority: P2)

**Goal**: A polished 6-field form with sensible defaults that users can submit in under 2 minutes without instructions.

**Independent Test**: Load the page — all 6 fields render with defaults. Set `end_time` to 30 minutes after `start_time` and submit — a warning appears without hitting the backend. Change all fields and submit — the correct values are sent to the API.

- [ ] T020 [P] [US2] Implement `PreferenceForm.vue` in `frontend/src/components/PreferenceForm.vue`: district dropdown (8 options, default `daan`), start/end time pickers (default 10:00–14:00), interests multi-select tags (vocabulary from contracts/api.md, default `["food","cafes"]`), budget radio (default `mid`), companion radio (default `solo`), indoor_pref radio (default `no_preference`); emit `submit` event with `UserPreferencesRequest`
  - **Validation**: All fields visible on page load with correct defaults; changing each field updates the emitted value; form is usable on a 375px mobile screen without horizontal scroll

- [ ] T021 [US2] Add client-side validation to `PreferenceForm.vue`: if `end_time − start_time < 60 min`, show inline warning "Please allow at least 1 hour" and disable the submit button; clear warning when time range is fixed
  - **Validation**: Set end_time 30 min after start_time → warning appears and button is disabled; set end_time 90 min after → warning clears and button re-enables; form never sends a 400-bound request to the backend

- [ ] T022 [US2] Add loading state to `PreferenceForm.vue`: disable submit button and show spinner while `isLoading` is true; re-enable on response or error
  - **Validation**: Submit the form — button shows spinner and is unclickable; after response arrives, button returns to normal; rapid double-click does not send two requests

- [ ] T023 [US2] Display API error messages in `PreferenceForm.vue`: catch `ErrorResponse` from `api.ts` and show `error.message` in a visible alert box above the form
  - **Validation**: Manually trigger a `time_range_too_short` error from the backend — message renders in the alert; message disappears on next successful submit

- [ ] T024 [US2] Wire `PreferenceForm` into `HomePage.vue` in `frontend/src/pages/HomePage.vue`: replace the hardcoded default-submit button with `<PreferenceForm @submit="handleSubmit" />`; pass submitted preferences to `api.ts`
  - **Validation**: Full preference form renders on the home page; changing fields and submitting sends the correct values to the API; loading/error states work end-to-end

**Checkpoint**: Users can fill in the form and submit preferences. Client-side validation prevents bad requests. Loading/error states provide feedback.

---

## Phase 5: US3 — Structured Itinerary Output Display (Priority: P2)

**Goal**: The itinerary response rendered as structured cards — not raw JSON.

**Independent Test**: Mock `ItineraryResponse` with 4 stops and pass it directly to `ItineraryDisplay` — all stop cards render in order with all required fields; the weather badge appears; cards are readable on a 375px screen.

- [ ] T025 [P] [US3] Implement `StopCard.vue` in `frontend/src/components/StopCard.vue`: display `order` badge, `name` (bold), `category` tag chip, `arrival_time`, `dwell_minutes`, `reason`, and (if not last stop) `travel_to_next_minutes`; accept a single `ItineraryStop` prop
  - **Validation**: Render with a mock stop — all fields visible; the travel-time indicator is hidden when `travel_to_next_minutes === 0`; card does not overflow horizontally on 375px viewport

- [ ] T026 [P] [US3] Implement `WeatherBadge.vue` in `frontend/src/components/WeatherBadge.vue`: display weather icon emoji (clear→☀️, cloudy→☁️, rain/drizzle→🌧️, thunderstorm→⛈️, unknown→—) and `temperature_c°C`; accept nullable `WeatherContext` prop; render nothing when prop is null
  - **Validation**: Pass `{ condition: "rain", temperature_c: 18 }` — badge shows "🌧️ 18°C"; pass `null` — no badge rendered; icons match all 5 condition values

- [ ] T027 [US3] Implement `ItineraryDisplay.vue` in `frontend/src/components/ItineraryDisplay.vue`: render `<WeatherBadge>` at top (hidden if `weather` is null), then a list of `<StopCard>` components in `stops[].order` ascending order; show metadata footnotes ("Nearby districts included", "Weather data unavailable") when `metadata` flags are set
  - **Validation**: Render a 4-stop response — cards appear in order 1→4; weather badge appears above cards; swapping order in mock data does not re-sort (component respects the API's order)

- [ ] T028 [US3] Add a full-page loading skeleton to `ItineraryDisplay.vue` area in `frontend/src/pages/HomePage.vue`: while `isLoading`, show 3 placeholder skeleton card divs (grey rectangles matching StopCard dimensions)
  - **Validation**: Submit form — skeleton cards appear immediately; itinerary replaces them on response; no layout shift when skeleton swaps to real cards

- [ ] T029 [US3] Replace raw JSON `<pre>` in `HomePage.vue` with `<ItineraryDisplay>` and verify mobile layout in `frontend/src/pages/HomePage.vue`: `<PreferenceForm>` and `<ItineraryDisplay>` stack vertically on mobile; side-by-side on ≥ 768px screens
  - **Validation**: Open on 375px viewport — form stacks above itinerary; open on 1024px — side-by-side; all stop fields readable at both sizes; no horizontal scrollbar

**Checkpoint**: Full end-to-end UI is functional. Form → loading skeleton → itinerary cards with weather badge. The product is visually demo-ready.

---

## Phase 6: US4 — Weather Context Integration (Priority: P3)

**Goal**: Live weather data from OpenWeatherMap influences the itinerary. Backend fetches, caches, and falls back gracefully.

**Independent Test**: Set `MOCK_WEATHER=rain` and POST to `/api/v1/itinerary` with `indoor_pref=no_preference` — response `weather.condition` is `"rain"` and ≥ 75% of stops are `indoor: true`. Remove `MOCK_WEATHER` and set an invalid API key — response still returns a valid itinerary with `metadata.weather_fallback: true`.

### Backend

- [ ] T030 [US4] Implement `WeatherService.fetch_weather()` in `backend/app/services/weather.py`: call `https://api.openweathermap.org/data/2.5/weather?q=Taipei,TW&units=metric&appid={key}`; map `weather[0].main` → condition enum (Clear→clear, Clouds→cloudy, Rain/Drizzle→rain, Thunderstorm→thunderstorm, else→unknown); return `WeatherContext`; respect `MOCK_WEATHER` env var — if set, return `WeatherContext(condition=MOCK_WEATHER)` without HTTP call
  - **Validation**: With valid API key, function returns a `WeatherContext` with non-null `temperature_c`; setting `MOCK_WEATHER=rain` returns `condition="rain"` without any network call; all 5 OWM condition strings map correctly

- [ ] T031 [US4] Add in-memory TTL cache to `WeatherService` in `backend/app/services/weather.py`: store `(WeatherContext, fetched_at)` in a module-level dict; return cached result if age < `settings.WEATHER_CACHE_TTL_MINUTES`; invalidate on new fetch
  - **Validation**: Call `fetch_weather()` twice within 1 minute — second call returns immediately (no HTTP request, verified by mocking); wait/mock time past TTL — third call makes a fresh HTTP request

- [ ] T032 [US4] Add fallback in `WeatherService` in `backend/app/services/weather.py`: wrap HTTP call in `try/except`; on any error (timeout, 401, 429, network failure), return `WeatherContext(condition="unknown", temperature_c=None)` and log a warning
  - **Validation**: Pass a bogus API key — function returns `WeatherContext(condition="unknown")` without raising; response `metadata.weather_fallback` is `true`; no 500 error surfaced to client

- [ ] T033 [US4] Wire `WeatherService` into `POST /api/v1/itinerary` in `backend/app/api/v1/itinerary.py`: call `fetch_weather()` before scoring; pass `WeatherContext` to `ScoringEngine.score()` and `ItineraryBuilder.build()`; set `metadata.weather_fallback` when condition is `"unknown"`
  - **Validation**: Response `weather` object is populated when API works; is `null` when API fails (fallback); `metadata.weather_fallback` accurately reflects which path was taken

- [ ] T034 [US4] Add `MOCK_WEATHER` tip to `backend/.env.example` and `quickstart.md`: document `MOCK_WEATHER=rain` for demo prep; add note that MOCK_WEATHER bypasses the real API
  - **Validation**: `.env.example` contains `MOCK_WEATHER=` with an inline comment; quickstart.md "Development Tips" section references it

**Checkpoint**: Weather integration complete. Rainy weather changes itinerary composition. Demo can be made reliable with `MOCK_WEATHER=rain`.

---

## Phase 7: US5 — Ranked Candidate Places (Priority: P3)

**Goal**: The full 4-component scoring formula is active. Weather influences rankings. Fallback ensures ≥ 3 stops are always returned.

**Independent Test**: POST with `indoor_pref=no_preference` and `MOCK_WEATHER=rain` — at least 75% of stops are `indoor: true`. POST with `interests=["food"]` in `daan` — all stops have `tags` containing `food` or `category` matching food/restaurant. POST with a rare combination that returns < 3 venues — response still has ≥ 3 stops (fallback triggered, `metadata.filter_relaxed: true`).

- [ ] T035 [US5] Add `weather_score` component to `ScoringEngine.score()` in `backend/app/services/scoring.py`: implement the full matrix from plan.md (rain+indoor=1.0, rain+outdoor=0.10, cloudy+outdoor=0.75, cloudy+indoor=0.80, clear+outdoor=1.0, clear+indoor=0.70, unknown=0.85); update formula weights to `interest*0.40 + weather*0.30 + trend*0.20 + budget*0.10`
  - **Validation**: Score an indoor venue under rain — weather component = 1.0; score an outdoor venue under rain — weather component = 0.10; scores change meaningfully between rain and clear conditions for the same venue

- [ ] T036 [US5] Add filter relaxation to `VenueRepository.filter()` in `backend/app/models/db.py`: if result count < 3, retry with district radius expanded to 5 km; if still < 3, retry again with `indoor_pref` relaxed to `no_preference`; set `filter_relaxed=True` flag in result metadata
  - **Validation**: Query a district with only 1 matching venue — function still returns ≥ 3 venues; the `filter_relaxed` flag is `True` in those cases; the `metadata.filter_relaxed` field in the API response reflects this

- [ ] T037 [P] [US5] Extract `haversine_km(lat1, lon1, lat2, lon2) -> float` utility in `backend/app/services/routing.py`: use the Haversine formula; validate with known Taipei distances (e.g. Da'an MRT to Taipei 101 ≈ 2.5 km)
  - **Validation**: `haversine_km(25.0336, 121.5320, 25.0339, 121.5645)` ≈ 2.5 (±0.3 km); function is pure (no side effects)

- [ ] T038 [P] [US5] Implement `GET /api/v1/venues` debug endpoint in `backend/app/api/v1/itinerary.py`: accept optional query params `district`, `category`, `indoor`, `limit` (default 100); return `{"total": N, "venues": [...]}` per contracts/api.md
  - **Validation**: `GET /api/v1/venues?district=daan` returns only Da'an venues; `GET /api/v1/venues?indoor=true` returns only indoor venues; response matches the contract schema

- [ ] T039 [US5] Validate rain-bias end-to-end in `backend/tests/test_scoring.py` (or manual smoke test): with `MOCK_WEATHER=rain` and `indoor_pref=no_preference`, assert ≥ 75% of returned stops are `indoor: true`; with `MOCK_WEATHER=clear`, assert outdoor stops appear in results
  - **Validation**: Test passes; if manually run: rain response has ≥ 3 of 4 stops as indoor; clear response includes at least 1 outdoor stop

**Checkpoint**: Full recommendation engine complete. Weather, interest, trend, and budget all influence rankings. Filter relaxation guarantees ≥ 3 stops always.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Production-quality error handling, automated tests, and demo readiness.

- [ ] T040 Add global exception handler to `backend/app/main.py`: catch unhandled exceptions and return `{"error_code":"itinerary_generation_failed","message":"...","request_id":"..."}` with HTTP 500; log the traceback server-side
  - **Validation**: Force a runtime error in a service — client receives a clean 500 JSON response (not a Python traceback); server logs the full exception

- [ ] T041 [P] Write `backend/tests/test_scoring.py`: test `weather_score` matrix for all 6 rain/clear × indoor/outdoor combinations; test `budget_score` lookup table for all 9 combinations; test `interest_score` with matching, partial, and zero-overlap tags
  - **Validation**: `pytest backend/tests/test_scoring.py -v` passes all assertions; 0 failures

- [ ] T042 [P] Write `backend/tests/test_api.py`: test `POST /api/v1/itinerary` happy path (default params → 200 with 3–5 stops); test `time_range_too_short` → 400; test `MOCK_WEATHER=rain` → stops ≥ 75% indoor; test weather API fallback → `metadata.weather_fallback: true`
  - **Validation**: `pytest backend/tests/test_api.py -v` passes all assertions; uses `httpx.AsyncClient` with `app` directly (no live server needed)

- [ ] T043 End-to-end demo dry run: start both `uvicorn` and `vite dev`; open browser at `http://localhost:5173`; submit default form; measure time from click to itinerary render; set `MOCK_WEATHER=rain` and verify UI shows rain badge and predominantly indoor stops
  - **Validation**: Itinerary renders in under 10 seconds; weather badge shows 🌧️ with temperature; at least 3 of 4 stops show `indoor: true` metadata visible in StopCard; no console errors; layout intact on 375px mobile emulation

- [ ] T044 (Stretch) Implement LLM explanation path in `backend/app/services/itinerary_builder.py`: when `USE_LLM=true`, for each stop construct a prompt with venue metadata + preferences + weather and call Claude or OpenAI with 2s timeout; fall back to template on timeout/error; run all stop LLM calls in parallel with `asyncio.gather`
  - **Validation**: Set `USE_LLM=true` with valid API key — reasons are notably richer than templates; set an invalid key — falls back to templates silently; total response time stays under 10 s

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
  └── Phase 2 (Foundation) ← BLOCKS all user stories
        ├── Phase 3 [US1] Core Pipeline  ← 🎯 MVP milestone
        ├── Phase 4 [US2] Preference Form
        ├── Phase 5 [US3] Output Display
        ├── Phase 6 [US4] Weather Integration ← depends on Phase 3 wiring
        ├── Phase 7 [US5] Full Scoring Engine ← depends on Phase 3 scoring
        └── Phase 8 Polish ← depends on Phase 3–7
```

### User Story Dependencies

| Story | Depends on | Can parallelize with |
|-------|-----------|---------------------|
| US1 — Core Pipeline | Phase 1, Phase 2 | US2, US3 (frontend) |
| US2 — Preference Form | Phase 1, Phase 2 | US1 (backend), US3 |
| US3 — Output Display | Phase 1, Phase 2 | US1 (backend), US2 |
| US4 — Weather Integration | Phase 2, US1 (T016 wired) | US2, US3 |
| US5 — Full Scoring Engine | Phase 2, US1 (T013 exists) | US2, US3 |

### Within Each Phase

- Foundation tasks T007 + T008 + T011 are fully parallel (different files)
- US1 backend tasks T013 + T014 + T015 are parallel (different service files)
- US3 tasks T025 + T026 are parallel (different component files)
- Tests T041 + T042 are parallel

---

## Parallel Example: Hackathon 2-Person Team

```
Developer A (Backend):               Developer B (Frontend):
Phase 1: T001, T002, T005            Phase 1: T003, T004
Phase 2: T006, T007, T009, T010      Phase 2: T008 (seed data), T011
US1:     T012, T013, T014, T015,     US2:     T020, T021, T022, T023
         T016, T017
US1:     T018 (api.ts)               US2/3:   T024, T025, T026, T027
US4:     T030, T031, T032, T033      US3:     T028, T029
US5:     T035, T036, T037, T038      Polish:  T040, T043
Tests:   T039, T041, T042            Stretch: T044
```

---

## Implementation Strategy

### Minimum Viable Demo (US1 only)

1. Complete Phase 1 (Setup) — T001–T005
2. Complete Phase 2 (Foundation) — T006–T011
3. Complete Phase 3 (US1 Core Pipeline) — T012–T019
4. **STOP and validate**: `POST /api/v1/itinerary` returns 3–5 stops in < 5 s; raw JSON renders in browser
5. This is a shippable demo — everything after is polish

### Full MVP (All 5 Stories)

1. Setup + Foundation (together, 1–2 h)
2. US1 backend + US2/US3 frontend in parallel (2–3 h)
3. US4 weather + US5 scoring engine in parallel (1–2 h)
4. Phase 8 polish + demo dry run (1 h)

### Hackathon Stop Points

- After T019: Can demo a working itinerary with raw JSON output
- After T029: Can demo a polished card-based UI
- After T034: Can demo weather-aware recommendations live
- After T043: Demo-ready with all success criteria verified

---

## Notes

- `[P]` tasks touch different files with no shared dependencies — safe to assign to different people simultaneously
- Each phase ends with a **Checkpoint** — stop and validate before moving on
- Validation criteria in each task are the literal "done" signal — if it passes, the task is complete
- The `MOCK_WEATHER` env var is your best friend for a reliable hackathon demo — set it before presenting
- Seed data quality (T008) directly determines itinerary quality — invest time here
- Total tasks: **44** (T001–T044, T044 is stretch)
