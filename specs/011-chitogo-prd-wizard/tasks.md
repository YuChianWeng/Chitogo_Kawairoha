# Tasks: ChitoGO PRD State-Machine Trip Wizard

**Input**: Design documents from `/specs/011-chitogo-prd-wizard/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/ ✅, research.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US8)
- Exact file paths are included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install new dependencies and prepare project structure.

- [X] T001 Add `rapidfuzz>=3.0` and `odfpy>=1.4` to `backend/Chat_Agent/requirements.txt`
- [X] T002 Add `vue-router@4` to `frontend/package.json` (run `npm install vue-router@4`)

**Checkpoint**: Dependencies installed — foundational work can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, FSM guard, router skeleton, and TypeScript types that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Extend `backend/Chat_Agent/app/session/models.py` — add `FlowState` enum (QUIZ/TRANSPORT/RECOMMENDING/RATING/ENDED), `AccommodationConfig`, `TransportConfig`, `VisitedStop`, `CandidateCard`, `ReachableCache` Pydantic models, and 13 new optional PRD fields on `Session` (flow_state, quiz_answers, travel_gene, mascot, accommodation, return_time, return_destination, transport_config, visited_stops, gene_affinity_weights, go_home_reminded_at, pending_venue, reachable_cache) per `data-model.md`
- [X] T004 Create `backend/Chat_Agent/app/api/v1/trip.py` as an empty `APIRouter(prefix="/api/v1/trip")` with a `SessionFSM.assert_state(session, *allowed)` helper that raises `ValueError("state_error:expected_{STATE}")` on violation; register the router in `backend/Chat_Agent/app/main.py` (depends on T003)
- [X] T005 [P] Create `frontend/src/types/trip.ts` with all TypeScript interfaces per `contracts/frontend-state.md`: `TravelGene`, `TransportMode`, `FlowState`, `QuizAnswers`, `QuizResult`, `AccommodationInput`, `TripSetup`, `SetupResult`, `HotelValidation`, `CandidateCard`, `CandidatesResult`, `SelectResult`, `RateResult`, `DemandResult`, `GoHomeStatus`, `VisitedStopSummary`, `JourneySummary`
- [X] T006 [P] Create `frontend/src/router/index.ts` with routes `/ → /quiz` redirect, `/quiz` (no guard), `/setup` (guard: `chitogo_session_id` in localStorage), `/trip` (guard: `chitogo_session_id` AND `chitogo_gene`), `/summary` (guard: `chitogo_session_id`); update `frontend/src/main.ts` to install the router via `app.use(router)`
- [X] T007 [P] Extend `frontend/src/services/api.ts` with 8 trip methods: `submitQuiz(sessionId, answers)`, `submitSetup(sessionId, setup)`, `getCandidates(sessionId, lat, lng)`, `selectVenue(sessionId, venueId, lat, lng)`, `submitRating(sessionId, stars, tags)`, `submitDemand(sessionId, text, lat, lng)`, `checkGoHome(sessionId, lat, lng)`, `getSummary(sessionId)` — all typed against `frontend/src/types/trip.ts`

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Preference Quiz & Travel Gene Onboarding (Priority: P1) 🎯 MVP

**Goal**: A new user opens the app, completes the 9-question quiz, and sees a travel gene result card with mascot and gene description.

**Independent Test**: Open `/quiz` in a browser → complete all 9 questions → see gene result card (one of 6 genes) with mascot identifier and description text.

- [X] T008 [US1] Create `backend/Chat_Agent/app/orchestration/gene_classifier.py` with `TravelGeneClassifier`: scoring matrix from `research.md` (Q1 → 文清+親子 for A, 野外+一日 for B, 夜貓子 for C; Q2-Q9 per matrix table), `classify(answers) → (gene, mascot, gene_description)`, tiebreaker logic (within-1-point → LLM fallback, then earliest-answer tie-break), `GENE_MASCOT_MAP` dict, and `GENE_DESCRIPTIONS` dict with short Chinese text for all 6 genes
- [X] T009 [US1] Implement `POST /api/v1/trip/quiz` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard QUIZ state, validate all 9 answers present (Q1: A/B/C, Q2-Q9: A/B), call `TravelGeneClassifier.classify()`, initialize `gene_affinity_weights` from gene's base affinity map, update session fields (travel_gene, mascot, quiz_answers, flow_state→TRANSPORT), return `QuizResult`
- [X] T010 [P] [US1] Create `frontend/src/pages/QuizPage.vue`: create session via `createSession()` on mount and store `chitogo_session_id` in localStorage; render one question at a time with progress bar ("第 N / 9 題"), option buttons (3 buttons for Q1, 2 buttons for Q2-Q9); on final answer call `submitQuiz()`, store `chitogo_gene` and `chitogo_mascot` in localStorage, display travel gene result card (gene name, mascot image `<img>` placeholder by mascot ID, gene description), then button to navigate to `/setup`
- [X] T011 [US1] Update `frontend/src/pages/HomePage.vue` to unconditionally redirect to `/quiz` using `router.push('/quiz')` on mount (repurpose as entry-point redirect, removing existing itinerary UI)

**Checkpoint**: User Story 1 independently functional — quiz → gene card complete

---

## Phase 4: User Story 2 — Trip Setup: Accommodation, Return Time & Transport (Priority: P1)

**Goal**: After the quiz, the user configures hotel/district, optional return time, and transport mode; the system validates hotel names against the legal registry.

**Independent Test**: Submit setup form with a hotel name → see validation badge (valid/fuzzy/not-found) and "Setup Complete" confirmation; subsequent API calls respect the stored transport config.

- [X] T012 [US2] Implement `POST /api/v1/trip/setup` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard TRANSPORT state; if `accommodation.booked=true` require `hotel_name` and call `PlaceToolAdapter.check_lodging_legal_status()` + `search_lodging_candidates()` (proxy to Data Service); validate `return_time` matches `HH:MM` regex; validate `transport.modes` non-empty and values in `{"walk","transit","drive"}`; update session (accommodation with validation results, return_time, return_destination, transport_config, flow_state→RECOMMENDING); return `SetupResult` with `hotel_validation` object per `contracts/trip-api.md`
- [X] T013 [P] [US2] Create `frontend/src/pages/SetupPage.vue`: booked/not-booked radio toggle; when booked=true show hotel name text input that calls `submitSetup()` on submit and renders validation feedback (green badge for `validated`/`fuzzy_match`, yellow warning with alternatives list for `not_found`, grayed for `not_required`); when booked=false show district `<select>` and budget_tier radio (budget/mid/luxury); optional return time `<input type="time">` and return destination text field; transport modes checkboxes (walk/transit/drive) and `max_minutes_per_leg` range slider (1-120, label shows value in minutes); submit button calls `submitSetup()` and navigates to `/trip` on success

**Checkpoint**: User Story 2 independently functional — setup form → validation → RECOMMENDING state

---

## Phase 5: User Story 3 — Six-Candidate Recommendation Loop (Priority: P1)

**Goal**: From a configured session the user sees 6 venue cards, selects one, navigates there, rates it, and returns to a fresh 6-candidate set — the full loop cycle works end-to-end.

**Independent Test**: Starting from RECOMMENDING state, call `GET /trip/candidates` → receive 6 cards (3 restaurant + 3 attraction); call `POST /trip/select` → receive navigation URLs + encouragement; call `POST /trip/rate` → session returns to RECOMMENDING with updated affinity weights.

- [X] T014 [US3] Create `backend/Chat_Agent/app/services/reachability.py` with `haversine_distance(lat1, lng1, lat2, lng2) → float` (km), `haversine_pre_filter(venues, origin_lat, origin_lng, max_minutes, mode) → list` (1.5× safety margin at 4.5 km/h walking equivalent), `async route_time_estimate(venue, origin, mode, semaphore) → int` (minutes, calls Google Maps or haversine fallback when `ROUTE_PROVIDER=fallback`), and `graduated_fallback(venues, ...) → (filtered, fallback_reason)` (extend +10 min → add transit → partial=True)
- [X] T015 [US3] Create `backend/Chat_Agent/app/services/candidate_picker.py` with `async pick_candidates(session, origin_lat, origin_lng) → CandidatesResult`: fetch venues from `PlaceToolAdapter`, apply `haversine_pre_filter`, call `route_time_estimate` with `asyncio.Semaphore(5)` via `asyncio.gather`, score by `session.gene_affinity_weights`, split into 3 restaurants + 3 attractions (partial fill on shortfall), single batch LLM call (Gemini 2.5 Flash) to generate `why_recommended` for all 6 cards in one JSON-array prompt, update `session.reachable_cache` (5-min TTL); and `async demand_mode(session, demand_text, origin_lat, origin_lng) → DemandResult`: LLM extracts intent → filter reachable venues → return 1-3 alternatives
- [X] T016 [US3] Implement `GET /api/v1/trip/candidates` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard RECOMMENDING, validate lat/lng in reasonable range, call `candidate_picker.pick_candidates()`, return `CandidatesResult` (partial flag, fallback_reason, restaurant_count, attraction_count)
- [X] T017 [US3] Implement `POST /api/v1/trip/select` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard RECOMMENDING, verify `venue_id` exists in the session's last candidate set (store last set in session after T016 call), set `session.pending_venue`, build Google Maps URL (`https://maps.google.com/?daddr={lat},{lng}&travelmode={mode}`) and Apple Maps URL (`maps://maps.apple.com/?daddr={lat},{lng}`), call LLM for 1-2 sentence `encouragement_message`, transition RECOMMENDING→RATING, return `SelectResult`
- [X] T018 [US3] Implement `POST /api/v1/trip/rate` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard RATING, validate `stars` 1-5, build `VisitedStop` from `session.pending_venue` + `arrived_at=now()` + `stars` + `tags`, append to `session.visited_stops`, update `session.gene_affinity_weights` (+0.2 for 5★, −0.3 for 1-2★ capped at 0, no change for 3-4★) for the venue's `category` and `primary_type`, clear `session.pending_venue`, transition RATING→RECOMMENDING, return `RateResult` with `affinity_update`
- [X] T019 [P] [US3] Create `frontend/src/components/CandidateGrid.vue`: render 6 `<div class="candidate-card">` items from `CandidatesResult.candidates`; each card shows venue name, category badge (`restaurant` vs `attraction` with distinct colors), `distance_min` in minutes, star rating display (numeric), `why_recommended` sentence; card click emits `select` event with `venue_id`; include `<button class="none-of-these">沒有想去的</button>` that emits `demand` event; show `fallback_reason` notice if `partial=true`
- [X] T020 [US3] Create `frontend/src/pages/TripPage.vue` as main loop container: `tripPhase` reactive ref initialized to `SELECTING`; on mount request geolocation (`navigator.geolocation.getCurrentPosition`), poll every 30s during SELECTING/NAVIGATING; call `getCandidates()` when SELECTING and render `<CandidateGrid>` passing candidates; when `select` event received call `selectVenue()` and transition to NAVIGATING; render `<NavigationPanel>` placeholder `<div>` when NAVIGATING with venue name and deep-link buttons; render `<RatingCard>` placeholder `<div>` when RATING with a basic 5-star input calling `submitRating()`; `<button class="go-home">我想回家</button>` fixed to bottom, visible in all phases except ENDED

**Checkpoint**: User Story 3 independently functional — full 6-candidate loop works end-to-end

---

## Phase 6: User Story 4 — Alternative Demand Mode (Priority: P2)

**Goal**: Tapping "沒有想去的" opens a demand modal; entering text replaces the grid with 3 alternative venue cards.

**Independent Test**: In SELECTING phase, tap "沒有想去的" → modal opens; enter demand text → 3 alternative cards render; tap one → session transitions to NAVIGATING.

- [X] T021 [US4] Implement `POST /api/v1/trip/demand` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard RECOMMENDING, validate `demand_text` not blank or whitespace-only, call `candidate_picker.demand_mode()`, return `DemandResult` (1-3 alternatives, fallback_reason)
- [X] T022 [P] [US4] Create `frontend/src/components/DemandModal.vue`: modal overlay with `<textarea>` for free-text input, placeholder text ("我想找有點文藝的地方"), submit button calling `submitDemand()`, results section rendering 1-3 `CandidateCard`-style items with name/category/distance/why_recommended; card click emits `select` event with venue; close button emits `close`
- [X] T023 [US4] Integrate `DemandModal.vue` into `frontend/src/pages/TripPage.vue`: `v-if` show modal when `demand` event from CandidateGrid fires; on `select` from DemandModal treat selection identically to regular grid selection (call `selectVenue()`, transition to NAVIGATING); on `close` hide modal and remain in SELECTING

**Checkpoint**: User Story 4 functional — demand mode works as escape valve from 6-candidate grid

---

## Phase 7: User Story 5 — Navigation to Selected Venue (Priority: P2)

**Goal**: After selecting a venue, a navigation screen shows destination details, Google Maps and Apple Maps deep-links, and an LLM encouragement message.

**Independent Test**: After `POST /trip/select`, the NavigationPanel shows venue address, tapping "開啟地圖" opens Google Maps deep-link, tapping "我到了！" transitions to RATING.

- [X] T024 [P] [US5] Create `frontend/src/components/NavigationPanel.vue`: display venue `name` and `address`, estimated travel time (`navigation.estimated_travel_min` in minutes), `<a>` button "開啟 Google Maps" linking to `navigation.google_maps_url`, `<a>` button "開啟 Apple Maps" linking to `navigation.apple_maps_url`, `<p class="encouragement">{{ encouragement_message }}</p>`, `<button>我到了！</button>` that emits `arrived` event
- [X] T025 [US5] Replace the NavigationPanel placeholder `<div>` in `frontend/src/pages/TripPage.vue` with `<NavigationPanel :venue="selectedVenue" :navigation="navData" :encouragement="encouragementMsg" @arrived="onArrived" />`; wire `onArrived` handler to transition `tripPhase` to `RATING`

**Checkpoint**: User Story 5 functional — navigation deep-links and encouragement message displayed

---

## Phase 8: User Story 6 — Post-Visit Rating (Priority: P2)

**Goal**: After arriving, the user rates with 1-5 stars and optional quick-tags; the rating updates gene affinity for subsequent recommendations.

**Independent Test**: In RATING state, tap 4 stars, select a quick-tag, submit → `RateResult.visit_recorded=true`; next `getCandidates()` call returns a set influenced by the updated affinity weights.

- [X] T026 [P] [US6] Create `frontend/src/components/RatingCard.vue`: show visited venue `name` and photo placeholder `<div class="photo-placeholder">`; 5-star interactive input (`<button v-for="n in 5">` toggling fill state); optional quick-tag chip buttons (`食物很好吃`, `人太多了`, `值得再來`, `服務很好`, `環境很棒`), multiple selectable; submit button calls `submitRating(stars, selectedTags)` and emits `rated` event with `RateResult`
- [X] T027 [US6] Replace RatingCard placeholder `<div>` in `frontend/src/pages/TripPage.vue` with `<RatingCard :venue="pendingVenue" @rated="onRated" />`; wire `onRated` handler to clear selected venue, transition `tripPhase` back to `SELECTING`, and call `getCandidates()` to load the next round (which now uses updated affinity weights)

**Checkpoint**: User Story 6 functional — full rating flow with affinity feedback closes the loop

---

## Phase 9: User Story 7 — Exit & Full Journey Summary (Priority: P3)

**Goal**: Tapping "我想回家" at any point ends the trip and displays a full journey timeline summary with mascot farewell.

**Independent Test**: Tap "我想回家" from SELECTING phase → confirmation modal → confirm → `/summary` page loads with chronological stop list, total elapsed time, total distance, and mascot farewell text.

- [X] T028 [US7] Implement `GET /api/v1/trip/summary` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard RECOMMENDING/RATING/ENDED; if not ENDED transition to ENDED; compute `JourneySummary`: `stops` = session.visited_stops in order, `total_stops` = len, `total_elapsed_min` = (last arrived_at − session.created_at).seconds // 60, `total_distance_m` = haversine sum over consecutive stop coordinates (import from `reachability.py`), `mascot_farewell` = LLM call with prompt including gene name + visited stop names + star ratings; return `JourneySummary` response per `contracts/trip-api.md`
- [X] T029 [P] [US7] Create `frontend/src/pages/SummaryPage.vue`: call `getSummary()` on mount using `chitogo_session_id` from localStorage; display mascot image placeholder keyed by `chitogo_mascot`; render chronological timeline cards each showing `stop_number`, `venue_name`, `arrived_at` formatted as `HH:mm`, `star_rating` as filled stars, `tags` as chips; show `total_elapsed_min` formatted as hours+minutes and `total_distance_m` in km; render `mascot_farewell` paragraph; share button using `navigator.share({ text: summary })` with `navigator.clipboard.writeText()` fallback
- [X] T030 [US7] Add "我想回家" confirmation modal to `frontend/src/pages/TripPage.vue`: clicking the fixed "我想回家" button opens a `<dialog>` with "確定要結束旅程嗎？" text and 確定/取消 buttons; 確定 calls `getSummary()` and on success calls `router.push('/summary')`; 取消 closes the dialog without state change

**Checkpoint**: User Story 7 functional — trip exit and summary timeline complete

---

## Phase 10: User Story 8 — "該回家了" Time-Based System Reminder (Priority: P3)

**Goal**: When calculated return time approaches, a non-blocking banner appears reminding the user to head home; it respects a 10-minute re-notification cooldown.

**Independent Test**: Set `return_time` to current time + 2 minutes in setup; within 60 seconds a banner appears with 繼續玩/回家去 buttons; tapping 繼續玩 hides the banner; no re-show for 10 minutes.

- [X] T031 [US8] Create `backend/Chat_Agent/app/services/go_home_advisor.py` with `calculate_trigger_time(return_time_str, transit_min) → datetime` (parse HH:MM → today's datetime, subtract transit_min + 30 min), `should_remind(session, current_transit_min) → bool` (check `datetime.now(UTC) >= trigger_time` AND `session.go_home_reminded_at` is None or > 10 minutes ago), and `record_reminded(session)` setting `session.go_home_reminded_at = now()`
- [X] T032 [US8] Implement `GET /api/v1/trip/should_go_home` in `backend/Chat_Agent/app/api/v1/trip.py`: FSM guard RECOMMENDING/RATING; if `session.return_time` is None return `remind=false`; estimate transit minutes from `lat/lng` to `session.return_destination` using `haversine_distance` (no Maps API call); call `go_home_advisor.should_remind()`; if true call `go_home_advisor.record_reminded(session)` and build reminder message; return `GoHomeStatus` with `time_remaining_min`
- [X] T033 [US8] Add "該回家了" banner to `frontend/src/pages/TripPage.vue`: `setInterval` every 60 seconds during SELECTING/NAVIGATING phases calling `checkGoHome()`; when `remind=true` show banner `<div class="go-home-banner">` with reminder message and two buttons: 繼續玩 (sets local `suppressUntil = Date.now() + 600_000` and hides banner without calling API) and 回家去 (calls `getSummary()` then `router.push('/summary')`); skip poll when `Date.now() < suppressUntil`; clear interval on component unmount

**Checkpoint**: User Story 8 functional — time-based reminder fires and respects cooldown

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Robustness improvements across all stories.

- [X] T034 [P] Add geolocation denied fallback to `frontend/src/pages/TripPage.vue`: detect `GeolocationPositionError.PERMISSION_DENIED`, show a `<div class="location-fallback">` banner with district `<select>` (大安區/信義區/中山區/…), on selection set `currentLat/currentLng` to district centroid coordinates used in all API calls
- [X] T035 [P] Audit all 8 endpoints in `backend/Chat_Agent/app/api/v1/trip.py` for correct error response format: every `ValueError("state_error:*")` must be caught by a FastAPI exception handler returning `{"detail": "state_error:..."}` with HTTP 400; `PlaceToolAdapter` network errors must return HTTP 503 `{"detail": "candidates_error:data_service_unavailable"}`; verify against the error table in `contracts/trip-api.md`
- [X] T036 [P] Verify `frontend/src/router/index.ts` route guards: navigate to `/setup` without localStorage → assert redirect to `/quiz`; navigate to `/trip` without `chitogo_gene` → assert redirect to `/quiz`; navigate to `/summary` without `chitogo_session_id` → assert redirect to `/quiz`; fix any guard logic gaps found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) — **BLOCKS all user story phases**
- **US1 (Phase 3)**: Depends on Phase 2 completion — no other story dependencies
- **US2 (Phase 4)**: Depends on Phase 2 completion — no dependency on US1
- **US3 (Phase 5)**: Depends on Phase 2 completion — no dependency on US1/US2 (but logically the full user flow requires US1+US2 first)
- **US4 (Phase 6)**: Depends on Phase 5 (requires `candidate_picker.py` to extend with `demand_mode`)
- **US5 (Phase 7)**: Depends on Phase 5 (backend `/trip/select` already returns navigation data; only frontend component needed)
- **US6 (Phase 8)**: Depends on Phase 5 (backend `/trip/rate` already handles affinity; only `RatingCard.vue` component needed)
- **US7 (Phase 9)**: Depends on Phase 5 (`visited_stops` only populated by POST /trip/rate)
- **US8 (Phase 10)**: Depends on Phase 2 (`GoHomeAdvisor` standalone service); frontend depends on Phase 5 (TripPage.vue must exist)
- **Polish (Phase 11)**: Depends on all desired stories complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — independent
- **US2 (P1)**: After Phase 2 — independent
- **US3 (P1)**: After Phase 2 — independent (backend service layer is self-contained)
- **US4 (P2)**: After US3 — requires `candidate_picker.py` from T015
- **US5 (P2)**: After US3 — requires `TripPage.vue` skeleton from T020
- **US6 (P2)**: After US3 — requires `TripPage.vue` skeleton from T020
- **US7 (P3)**: After US3 — requires `session.visited_stops` populated by T018
- **US8 (P3)**: After Phase 2 (backend) and after US3 (frontend)

### Within Each Phase

- Backend models before services; services before endpoints
- FSM guard (T003-T004) before any endpoint implementation
- TypeScript types (T005) before `api.ts` methods (T007)

---

## Parallel Execution Examples

### Phase 2 (Foundational) — after T003 completes

```
T003 (session/models.py) THEN:
  ├── T004 (trip.py router skeleton)   [backend]
  ├── T005 (trip.ts types)             [frontend — parallel with T004]
  ├── T006 (router/index.ts)           [frontend — parallel with T004]
  └── T007 (api.ts methods)            [frontend — parallel with T004]
```

### Phase 3 (US1) — all can start after T003/T004

```
T008 (gene_classifier.py)   ─── then T009 (quiz endpoint)
T010 (QuizPage.vue)         [parallel with T008/T009 — different file]
T011 (HomePage redirect)    [parallel with all — tiny independent change]
```

### Phase 5 (US3) — sequential backend, parallel frontend

```
T014 (reachability.py) THEN T015 (candidate_picker.py) THEN:
  ├── T016 (GET /candidates endpoint)
  ├── T017 (POST /select endpoint)
  └── T018 (POST /rate endpoint)
T019 (CandidateGrid.vue)    [parallel with T014-T018 — frontend only]
T020 (TripPage.vue)         [parallel with T014-T018 — frontend only]
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 only — Phases 1-5)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational) — **critical blocker**
3. Complete Phase 3 (US1: Quiz + Gene)
4. Complete Phase 4 (US2: Setup Form)
5. Complete Phase 5 (US3: 6-Candidate Loop)
6. **STOP and VALIDATE**: Full flow quiz → setup → candidates → select → rate → repeat
7. Demo-ready: core trip wizard working end-to-end

### Full Feature Delivery (all 8 stories)

After MVP validation:
1. Phase 6 (US4: Demand Mode) — adds escape valve
2. Phase 7 (US5: NavigationPanel) — polished navigation screen
3. Phase 8 (US6: RatingCard) — polished rating with quick-tags
4. Phase 9 (US7: Summary) — journey summary page
5. Phase 10 (US8: Go-Home Reminder) — time-based safety net
6. Phase 11 (Polish) — error handling, fallbacks, guard validation

### Parallel Team Strategy (3 developers after Phase 2)

- **Dev A**: US1 (gene classifier + quiz page) → US2 (setup endpoint + page)
- **Dev B**: US3 backend (reachability + candidate_picker + endpoints)
- **Dev C**: US3 frontend (CandidateGrid + TripPage skeleton) → US5/US6 components

---

## Summary

| Phase | Stories | Tasks | Key Deliverable |
|-------|---------|-------|-----------------|
| 1 Setup | — | T001-T002 | Dependencies installed |
| 2 Foundational | — | T003-T007 | Session models, FSM, router, TS types |
| 3 US1 (P1) | Quiz + Gene | T008-T011 | 9-question quiz → travel gene card |
| 4 US2 (P1) | Setup Form | T012-T013 | Hotel validation + transport config |
| 5 US3 (P1) | Rec Loop | T014-T020 | Full 6-candidate loop (core product) |
| 6 US4 (P2) | Demand Mode | T021-T023 | "None of these" → 3 alternatives |
| 7 US5 (P2) | Navigation | T024-T025 | NavigationPanel with map deep-links |
| 8 US6 (P2) | Rating | T026-T027 | RatingCard with quick-tags + affinity |
| 9 US7 (P3) | Summary | T028-T030 | Journey timeline + mascot farewell |
| 10 US8 (P3) | Go-Home | T031-T033 | Time-based reminder banner + cooldown |
| 11 Polish | — | T034-T036 | Geo fallback, error handling, guards |
| **Total** | **8 stories** | **36 tasks** | **Full PRD wizard** |

**Suggested MVP scope**: Phases 1–5 (T001–T020, 20 tasks) — delivers the complete core trip experience.
