---
description: "Task list for feature 003-agent-orchestration-backend implementation"
---

# Tasks: Agent Orchestration Backend

**Input**: Design documents from `specs/003-agent-orchestration-backend/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/chat-api.md, contracts/tools.md

**Tests**: Test tasks are included throughout — both unit and integration. Tests are required for the route fallback path, replanning preservation guarantee, session lifecycle/TTL, and the chat API contract per the spec's Success Criteria (SC-003, SC-005, SC-006).

**Organization**: Tasks are organized by **implementation phase** as requested in the spec-kit input. Each task is also tagged with the user story it primarily serves (US1 = Itinerary Generation, US2 = Preference Extraction, US3 = Replanning, US4 = Explainable Responses) so traceability to spec.md is preserved.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[USn]**: Maps task to a user story from spec.md
- All paths are absolute under `/home/ubuntu/Chitogo_Kawairoha/backend/Chat_Agent/`

---

## Phase 1: Foundation

**Acceptance target**: `uvicorn app.main:app` boots, `GET /api/v1/health` returns 200 with a `data_service` field, environment variables are validated at startup, and `pytest` collects (zero tests passing is fine).

- [ ] T001 Create directory tree `app/`, `app/api/v1/`, `app/session/`, `app/orchestration/`, `app/tools/`, `app/llm/`, `tests/unit/`, `tests/integration/`, `tests/contract/` under `backend/Chat_Agent/` with empty `__init__.py` files
- [ ] T002 Create `backend/Chat_Agent/requirements.txt` with pinned versions: fastapi==0.111.*, uvicorn[standard], pydantic==2.*, httpx, anthropic, pytest, pytest-asyncio, pytest-cov, respx (httpx mock transport), loguru
- [ ] T003 Create `backend/Chat_Agent/app/config.py` exposing a `Settings` class (Pydantic BaseSettings) with `data_service_url`, `google_maps_api_key`, `anthropic_api_key`, `session_ttl_min=30`, `agent_loop_max_iterations=6`, `request_timeout_s=2`, `default_start_time="10:00"`; loads from env, fails fast on missing keys
- [ ] T004 [P] Create `backend/Chat_Agent/app/llm/client.py` with a thin Anthropic client wrapper that returns a singleton `AsyncAnthropic` instance using `Settings.anthropic_api_key`; expose default model `claude-sonnet-4-6` and a fallback model `claude-haiku-4-5-20251001`
- [ ] T005 [P] Create `backend/Chat_Agent/app/api/v1/health.py` with `GET /health` that probes `Settings.data_service_url + /api/v1/places/stats` (1 s timeout) and returns `{status, data_service}` where `data_service` is `"reachable"` or `"degraded"`
- [ ] T006 Create `backend/Chat_Agent/app/main.py` FastAPI entrypoint: instantiate FastAPI with `title="Chitogo Chat Agent"`, mount the v1 router under `/api/v1`, register the TTL sweeper as a startup task placeholder (filled by T015), include CORS middleware permissive for hackathon
- [ ] T007 [P] Create `backend/Chat_Agent/app/api/v1/__init__.py` exporting an `APIRouter` instance and including `health.router`
- [ ] T008 [P] Add `backend/Chat_Agent/.env.example` documenting all required env vars and `backend/Chat_Agent/README.md` with the install/run commands from `quickstart.md`
- [ ] T009 [P] Create `backend/Chat_Agent/pytest.ini` configuring `asyncio_mode = auto`, test paths `tests/`, and `addopts = -ra --strict-markers`
- [ ] T010 [P] Smoke test `tests/unit/test_config.py`: assert `Settings()` raises when required env vars missing and accepts when set via monkeypatch

**Checkpoint**: Service boots clean, health endpoint reports Data Service status, config validation works.

---

## Phase 2: Session and State

**Acceptance target**: A `SessionManager.get_or_create(uuid)` call creates and returns an empty session with all default fields; touching it updates `last_active_at`; sessions older than TTL are reaped by the background sweeper; two concurrent sessions never leak state into each other.

- [ ] T011 [P] Create `backend/Chat_Agent/app/session/models.py` with Pydantic v2 models per `data-model.md`: `TimeWindow`, `Preferences`, `Turn`, `Stop`, `Leg`, `Itinerary`, `Place`, `ToolCallRecord`, `TraceEntry`, `Session` — include all field-level constraints documented in data-model.md
- [ ] T012 [US1] Add `Itinerary.model_validator` enforcing dense `stop_index`, `len(legs) == len(stops) - 1`, and `total_duration_min` consistency
- [ ] T013 [US1] Add `Stop.field_validator` for `arrival_time` regex `^\d{2}:\d{2}$` and `category` membership in the 7 internal categories
- [ ] T014 Create `backend/Chat_Agent/app/session/store.py` with `InMemorySessionStore` class: `dict[UUID, Session]` guarded by `asyncio.Lock`; methods `get`, `put`, `touch`, `delete`, `all_session_ids`; expose a module-level singleton `_store`
- [ ] T015 Add `start_ttl_sweeper(store, ttl_min)` async function in `backend/Chat_Agent/app/session/store.py` that runs every 60 s and deletes sessions where `now - last_active_at > ttl_min minutes`; wire into `app/main.py` startup as an asyncio task; cancel on shutdown
- [ ] T016 [P] Create `backend/Chat_Agent/app/session/manager.py` with `SessionManager.get_or_create(session_id_str: str) -> tuple[Session, bool]` (returns session + `recreated` flag); validates UUID format and raises `InvalidSessionIdError` on malformed input; calls `store.touch` on access
- [ ] T017 [P] [US2] Add `SessionManager.append_turn(session, role, content) -> Turn` and `SessionManager.update_preferences(session, delta: Preferences)` helpers in `backend/Chat_Agent/app/session/manager.py`
- [ ] T018 [P] [US3] Add `SessionManager.set_itinerary(session, itinerary)` and `SessionManager.cache_candidates(session, places)` helpers in `backend/Chat_Agent/app/session/manager.py`
- [ ] T019 [P] Test `tests/unit/test_session_models.py`: assert validators reject malformed `arrival_time`, sparse `stop_index`, mismatched leg/stop lengths
- [ ] T020 [P] Test `tests/unit/test_session_store.py`: put/get/touch/delete round-trip, `all_session_ids` returns expected set, lock prevents concurrent corruption (use `asyncio.gather` of 100 concurrent puts)
- [ ] T021 [P] Test `tests/unit/test_session_manager.py`: `get_or_create` creates on first call, returns same instance on second, raises on bad UUID, `recreated` flag false on first/true after manual delete
- [ ] T022 Test `tests/integration/test_session_lifecycle.py`: monkeypatch `SESSION_TTL_MIN` to fractional value, run sweeper directly, assert idle session evicted; second test: create two sessions with different preferences, mutate one, assert the other is untouched (SC-005 isolation)

**Checkpoint**: Session lifecycle is fully working and tested. Subsequent phases can rely on `SessionManager` for state persistence.

---

## Phase 3: Planner and Preference Extraction

**Acceptance target**: A user message of arbitrary phrasing is classified into one of the 4 intents with appropriate slots; preferences from prior turns merge correctly into the session and are not silently overwritten by partial extracts; vague itinerary requests trigger `needs_clarification=True`.

- [ ] T023 [P] Create `backend/Chat_Agent/app/orchestration/intents.py` with `Intent` enum (`GENERATE_ITINERARY`, `REPLAN`, `EXPLAIN`, `CHAT_GENERAL`) and Pydantic slot schemas per `data-model.md` (`GenerateItinerarySlots`, `ReplanSlots`, `ExplainSlots`, `ChatGeneralSlots`)
- [ ] T024 [P] Create `backend/Chat_Agent/app/orchestration/classifier_rules.py` with deterministic rule definitions: `GENERATE_ITINERARY` (regex matches "plan", "itinerary", "day in", "trip"), `REPLAN` (regex "replace", "swap", "change stop \d+", "instead of"), `EXPLAIN` (starts with "why", "how come", "explain"); each rule returns `Optional[(Intent, slots_dict, confidence)]`
- [ ] T025 Create `backend/Chat_Agent/app/orchestration/classifier.py` `IntentClassifier` class with `classify(message: str, has_itinerary: bool) -> ClassifierResult`; first runs rules from T024; if no rule fires with confidence ≥ 0.8, calls Claude Haiku with a strict-JSON prompt and returns parsed result; bounds LLM call to 1 s
- [ ] T026 [US1] Add missing-info detection in `classifier.py`: when intent is `GENERATE_ITINERARY` and slots contain neither `districts` nor `categories` nor `duration_hint`, set `slots.needs_clarification = True`
- [ ] T027 [US3] Add `stop_index` extraction in `classifier_rules.py` for `REPLAN` (regex `stop\s+(\d+)` and ordinal "the second stop" → 1)
- [ ] T028 [P] [US2] Create `backend/Chat_Agent/app/orchestration/preferences.py` `PreferenceExtractor` class with `extract(message: str, current: Preferences) -> Preferences`; single Claude Sonnet call returning a JSON delta; merge logic: lists overwrite, scalars overwrite when present, missing keys preserved
- [ ] T029 [US2] Add `_detect_language(message)` helper in `preferences.py` using Unicode-block check (CJK Unified Ideographs → `zh-TW`, otherwise `en`); set `preferences.language` in extracted delta
- [ ] T030 [P] Test `tests/unit/test_classifier_rules.py`: 30+ message → expected-intent fixtures covering each intent and ambiguous cases (e.g., "show me food", "give me a 2-hour plan", "swap stop 1", "why this order")
- [ ] T031 [P] Test `tests/unit/test_classifier.py`: with rules-mock and LLM-mock, assert rule path skips LLM, ambiguous path hits LLM, LLM result is parsed into the typed slot model; `needs_clarification` is set when slots are empty for `GENERATE_ITINERARY`
- [ ] T032 [P] [US2] Test `tests/unit/test_preferences.py`: extract from "I'm vegetarian" produces `dietary=["vegetarian"]`; later extract from "I'm fine with crowds at night" preserves dietary and updates `crowd_tolerance`; correction "actually I eat meat" overwrites dietary
- [ ] T033 [P] [US2] Test `tests/unit/test_language_detection.py`: English string returns `en`, Traditional Chinese string returns `zh-TW`, mixed string returns `zh-TW`

**Checkpoint**: Classifier and preference extraction work end-to-end with mocked LLM. Wired into the pipeline in Phase 5.

---

## Phase 4: Tool Adapters

**Acceptance target**: All 6 Data Service retrieval endpoints are reachable through `PlaceToolAdapter`; Google Maps Transit calls return live data when available; route adapter falls back to haversine on every failure mode (timeout, 5xx, malformed body, no-route) without raising; tool registry exposes a different tool subset per intent.

- [ ] T034 [P] Create `backend/Chat_Agent/app/tools/errors.py` with `PlaceToolError` exception class (carries `status_code`, `detail`, `tool_name`)
- [ ] T035 Create `backend/Chat_Agent/app/tools/place_adapter.py` `PlaceToolAdapter` class: shared `httpx.AsyncClient(base_url=settings.data_service_url, timeout=settings.request_timeout_s)`; method `search(params: PlaceSearchParams) -> PlaceListResult` calling `GET /api/v1/places/search`
- [ ] T036 [P] Add `PlaceToolAdapter.recommend(params) -> PlaceListResult` calling `POST /api/v1/places/recommend` per contracts/tools.md
- [ ] T037 [P] Add `PlaceToolAdapter.nearby(params) -> NearbyListResult` calling `GET /api/v1/places/nearby` per contracts/tools.md
- [ ] T038 [P] Add `PlaceToolAdapter.batch(place_ids: list[int]) -> list[PlaceDetail]` calling `POST /api/v1/places/batch`
- [ ] T039 [P] Add `PlaceToolAdapter.categories() -> list[Category]` and `PlaceToolAdapter.stats() -> PlaceStats` calling the corresponding `GET` endpoints
- [ ] T040 Add error normalization in `place_adapter.py`: a single `_request` helper that catches `httpx.HTTPError`, non-2xx, and JSON parse errors; raises `PlaceToolError` with normalized fields; one retry on 5xx with 200 ms backoff
- [ ] T041 Create `backend/Chat_Agent/app/tools/route_fallback.py` with `haversine_km(from_lat, from_lng, to_lat, to_lng) -> float` and `fallback_estimate(from_lat, from_lng, to_lat, to_lng) -> RouteResult` (uses 12 km/h per R-004; returns `transit_method="estimated"`, `estimated=True`, rounded-up `duration_min`)
- [ ] T042 Create `backend/Chat_Agent/app/tools/route_adapter.py` `RouteToolAdapter` class with shared `httpx.AsyncClient(timeout=settings.request_timeout_s)` and method `estimate_leg(from_lat, from_lng, to_lat, to_lng, depart_at=None) -> RouteResult` calling Google Maps Directions API with `mode=transit`; on ANY exception or non-2xx OR `routes[]` empty, calls `fallback_estimate` from T041 and returns its result; never raises
- [ ] T043 Create `backend/Chat_Agent/app/tools/registry.py` `ToolRegistry` class: holds tool definitions in Anthropic tool-use format (per contracts/tools.md); method `tools_for(intent: Intent) -> list[ToolSchema]` returning the filtered subset per R-011 (e.g., `EXPLAIN` → `[]`, `CHAT_GENERAL` → `[place_search]`)
- [ ] T044 Add `ToolRegistry.dispatch(name: str, args: dict) -> Any` that routes a tool-use call from the LLM loop to the correct adapter method (mapping by name); records timing; returns the adapter result
- [ ] T045 [P] Test `tests/integration/test_place_adapter.py` using `respx`: mock each Data Service endpoint with happy-path JSON matching `app/Chitogo_DataBase/app/schemas/retrieval.py` shapes; assert each adapter method returns correctly typed Pydantic objects
- [ ] T046 [P] Test `tests/integration/test_place_adapter_errors.py` using `respx`: simulate timeout, 500, malformed JSON; assert `PlaceToolError` raised with normalized fields; assert one retry occurs on 5xx
- [ ] T047 [P] Test `tests/unit/test_route_fallback.py`: known coord pair (Taipei 101 → Longshan Temple) returns expected haversine ≈ 6 km / 12 km/h ≈ 30 min; `estimated=True` always
- [ ] T048 [P] Test `tests/integration/test_route_adapter.py` using `respx`: happy-path Google response → returns `transit_method="transit"`, `estimated=False`; timeout → fallback used; non-2xx → fallback used; empty `routes[]` → fallback used; in EVERY failure path the adapter does NOT raise (SC-006)
- [ ] T049 [P] Test `tests/unit/test_tool_registry.py`: `tools_for(EXPLAIN)` returns empty list; `tools_for(CHAT_GENERAL)` returns only `place_search`; `tools_for(GENERATE_ITINERARY)` returns the full place set + route_estimate; `dispatch("place_search", {…})` calls the right adapter method

**Checkpoint**: Tool layer is fully decoupled, tested, and ready to be invoked by the agent loop. Place + route data accessible only through these adapters.

---

## Phase 5: Recommendation Flow

**Acceptance target**: `POST /api/v1/chat/message` accepts a UUID + message and returns a structured response. For `CHAT_GENERAL` intent, the agent loop runs with only `place_search` exposed and produces a relevant reply with `itinerary=null`. End-to-end latency stays under 10 s with mocked LLM.

- [ ] T050 Create `backend/Chat_Agent/app/orchestration/agent_loop.py` `AgentLoop` class with `run(intent, slots, session, tools) -> LoopResult`; uses Anthropic tool-use API; bounded to `settings.agent_loop_max_iterations`; on each iteration: send conversation + accumulated tool results to LLM, parse tool_use blocks, dispatch each via `ToolRegistry.dispatch`, append `ToolCallRecord` to `LoopResult.tool_calls`; terminates when LLM returns plain text
- [ ] T051 Add system-prompt builder in `agent_loop.py` that includes: user preferences summary, current itinerary summary if present, the language hint (`User language: en|zh-TW`), and a clear directive that the LLM must not invent venues outside tool results
- [ ] T052 Add `LoopResult` model in `agent_loop.py`: `{narrative: str, tool_calls: list[ToolCallRecord], chosen_venue_ids: list[int] | None, route_results: list[RouteResult] | None, raw_messages: list[dict]}`
- [ ] T053 [P] Create `backend/Chat_Agent/app/orchestration/composer.py` `ResponseComposer` class with `compose_recommendation(loop_result, session, intent) -> ChatResponse` that wraps the LLM narrative with `itinerary=null`, sets `routing_status="full"`, and packages the response payload
- [ ] T054 Create `backend/Chat_Agent/app/api/v1/chat_models.py` Pydantic models for `ChatMessageRequest`, `ChatResponse`, `StopOut`, `LegOut`, `ItineraryOut` matching `contracts/chat-api.md` exactly
- [ ] T055 Create `backend/Chat_Agent/app/orchestration/handler.py` `MessageHandler.handle(request: ChatMessageRequest) -> ChatResponse` orchestrating the full per-turn pipeline: get_or_create session → append user turn → classify → extract preferences → run agent loop → compose → append assistant turn → return; pure function, no I/O outside collaborators
- [ ] T056 Create `backend/Chat_Agent/app/api/v1/chat.py` with `POST /chat/message` endpoint that delegates to `MessageHandler.handle`; map `InvalidSessionIdError` → 400, `PlaceToolError` (when fully unrecoverable) → 502, others → 500; include `intent_classified` in response
- [ ] T057 Wire `chat.router` and `health.router` into `app/api/v1/__init__.py` and verify they show up at `/api/v1/chat/message` and `/api/v1/health`
- [ ] T058 [P] Add `GET /chat/session/{session_id}` and `DELETE /chat/session/{session_id}` endpoints in `app/api/v1/chat.py` per contracts/chat-api.md (traces excluded by default; query param `?include=traces` opt-in)
- [ ] T059 [P] Test `tests/contract/test_chat_api_contract.py`: validate that the `ChatResponse` Pydantic model matches every field/type documented in `contracts/chat-api.md`
- [ ] T060 [P] Test `tests/integration/test_chat_endpoint_recommend.py`: with mocked LLM that emits a `place_search` tool_use then plain text, mocked `PlaceToolAdapter` returning 5 venues, send message "vegetarian restaurants near Ximending" with a fresh UUID; assert response has `intent_classified="CHAT_GENERAL"`, `itinerary=null`, `reply_text` non-empty, `session_recreated=false`
- [ ] T061 [P] Test `tests/integration/test_chat_endpoint_invalid.py`: assert `400` on malformed UUID; assert `400` on `message` length > 4000
- [ ] T062 [P] [US4] Test `tests/integration/test_chat_endpoint_explain.py`: with mocked LLM, send "Why did you pick Longshan Temple?" — assert `intent_classified="EXPLAIN"`, no tool calls dispatched (verify via tool registry mock), `reply_text` references at least one preference value from the mocked session

**Checkpoint**: Frontend can POST messages and get structured replies for non-itinerary intents. Session lifecycle, classification, preference extraction, tool routing, and LLM loop all wired together.

---

## Phase 6: Itinerary and Replanning

**Acceptance target**: A `GENERATE_ITINERARY` request produces a structured `Itinerary` with stops + legs + narrative. A `REPLAN` request that targets stop N preserves all other stops byte-for-byte and recomputes only the two affected legs. Route fallback degrades to `routing_status="partial_fallback"` or `"failed"` correctly.

- [ ] T063 [P] [US1] Create `backend/Chat_Agent/app/orchestration/itinerary.py` `ItineraryBuilder` class with pure-logic method `build(chosen_places: list[Place], leg_results: list[RouteResult], start_time: str, language: str) -> Itinerary`; uses category-based default `visit_duration_min` per R-007; computes `arrival_time` sequentially from `start_time`; assigns dense `stop_index` 0..N-1
- [ ] T064 [US1] Add `ItineraryBuilder._compute_routing_status(legs) -> str` returning `"full"` / `"partial_fallback"` / `"failed"` per the rule in contracts/tools.md
- [ ] T065 [US1] Add `ItineraryBuilder.summarize(itinerary, preferences) -> str` returning a 1-line summary like "Half-day in Ximending (vegetarian-friendly)" — purely templated, no LLM
- [ ] T066 [US1] Extend `ResponseComposer` (in `composer.py`) with `compose_itinerary(loop_result, session, intent) -> ChatResponse`: invokes `ItineraryBuilder.build` using `loop_result.chosen_venue_ids` (resolved via `session.candidate_places` lookup) and `loop_result.route_results`; sets `routing_status` from leg flags; appends partial-fallback note to `reply_text` when applicable
- [ ] T067 [US1] Update `MessageHandler.handle` in `app/orchestration/handler.py` to dispatch to `compose_itinerary` for `GENERATE_ITINERARY`; cache returned candidate set into `session.candidate_places` for replanning; call `SessionManager.set_itinerary`
- [ ] T068 [P] [US3] Create `backend/Chat_Agent/app/orchestration/replanner.py` `Replanner` class with method `replace_stop(itinerary: Itinerary, stop_index: int, new_place: Place, prev_leg: RouteResult, next_leg: RouteResult) -> Itinerary`; preserves all stops at indices != stop_index byte-for-byte; recomputes only legs `(stop_index-1, stop_index)` and `(stop_index, stop_index+1)`; recomputes `total_duration_min`; reassigns `arrival_time` for stop_index and all subsequent stops
- [ ] T069 [US3] Handle edge cases in `Replanner.replace_stop`: `stop_index == 0` (no prev leg, only next leg recomputed); `stop_index == len(stops) - 1` (no next leg); `stop_index` out of range → raise `ReplanRangeError`
- [ ] T070 [US3] Extend `ResponseComposer` with `compose_replan(loop_result, session, intent, slots) -> ChatResponse`: looks up stop_index from `slots`; if out of range or no current itinerary, returns explanatory `reply_text` without mutation; otherwise calls `Replanner.replace_stop`, updates session, returns response
- [ ] T071 [US3] Update `MessageHandler.handle` to dispatch to `compose_replan` for `REPLAN` intent
- [ ] T072 [US1] Update `MessageHandler.handle` to short-circuit `GENERATE_ITINERARY` with `slots.needs_clarification=True`: skip the agent loop, return a clarifying-question `reply_text` (templated per language) with `itinerary=null` (fulfills spec acceptance scenario US1.3)
- [ ] T073 [P] [US1] Test `tests/unit/test_itinerary_builder.py`: build with 3 places + 2 leg results, assert dense stop_index, monotonically increasing arrival_time, total_duration_min equals sum of visit + leg durations; per-category defaults from R-007 applied
- [ ] T074 [P] [US1] Test `tests/unit/test_routing_status.py`: all-live legs → `"full"`; one estimated → `"partial_fallback"`; all estimated → `"failed"`
- [ ] T075 [P] [US3] Test `tests/unit/test_replanner_preservation.py` (property test): for a 4-stop itinerary, replace each non-edge stop_index in turn; assert byte-for-byte equality of stops and legs at non-target indices using `Itinerary.model_dump()` comparison (SC-003)
- [ ] T076 [P] [US3] Test `tests/unit/test_replanner_edges.py`: replace stop 0 (only next leg recomputed); replace last stop (only prev leg recomputed); out-of-range index raises `ReplanRangeError`
- [ ] T077 [P] [US1] Test `tests/integration/test_chat_endpoint_itinerary.py`: with mocked LLM emitting `place_recommend` + `place_recommend` + 3× `route_estimate` + plain narrative, mocked adapters returning canned data; send "Plan a half-day in Ximending"; assert response has populated `itinerary` with 4 stops, 3 legs, `routing_status="full"`, `total_duration_min` consistent
- [ ] T078 [P] [US1] Test `tests/integration/test_chat_endpoint_fallback.py`: same as T077 but mock `RouteToolAdapter` to fall back on 1 of 3 legs; assert `routing_status="partial_fallback"`, that leg has `estimated=true`, others `false`, `reply_text` includes a note about the estimated leg
- [ ] T079 [P] [US3] Test `tests/integration/test_chat_endpoint_replan.py`: turn 1 generates a 4-stop itinerary (mocked); turn 2 sends "Replace stop 2 with a temple" (LLM mocked to call `place_nearby` + 2× `route_estimate`); assert turn-2 response stops 0, 1, 3 are byte-for-byte identical to turn-1 response, stop 2 is new
- [ ] T080 [P] [US1] Test `tests/integration/test_chat_endpoint_clarify.py`: send "Plan something" with no other context; assert `intent_classified="GENERATE_ITINERARY"`, `itinerary=null`, `reply_text` contains a question

**Checkpoint**: Full itinerary generation, replanning, and route fallback all working end-to-end. Spec acceptance scenarios for US1, US3 covered.

---

## Phase 7: Observability and Hardening

**Acceptance target**: Every turn writes a complete `TraceEntry` to `session.traces` (capped at 50). `GET /chat/session/{id}/trace` returns the full trace for the demo "show your work" panel. Latency is measured per tool call and per turn. The service handles 50 concurrent sessions without state leak. Quickstart demo flows all pass.

- [ ] T081 Create `backend/Chat_Agent/app/orchestration/trace.py` `TraceRecorder` class with `start_turn(session, intent) -> TraceContext` and `TraceContext.finish(composer_output, status)`; `TraceContext` has `add_tool_call(record)` method invoked by `ToolRegistry.dispatch`
- [ ] T082 Wire `TraceContext` into `MessageHandler.handle`: open a context at the start of each turn, pass it to `ToolRegistry.dispatch` (via dependency injection or contextvar), close with composer output and `final_status`; computes `total_latency_ms` from start/finish wall-clock; sets `fallback_used = any(leg.estimated for leg in itinerary.legs) if itinerary else False`
- [ ] T083 Add 50-entry FIFO eviction in `TraceRecorder.finish` when appending: if `len(session.traces) >= 50`, pop the oldest before append
- [ ] T084 Truncate large tool-call outputs in `ToolRegistry.dispatch`: if `output` is a list with > 50 items, store only first 50 + `_truncated_total` field — keeps memory bounded per R-009
- [ ] T085 [P] Add `GET /api/v1/chat/session/{session_id}/trace` endpoint in `app/api/v1/chat.py` returning `{session_id, count, traces}`; 404 if session unknown
- [ ] T086 [P] Configure structured logging in `backend/Chat_Agent/app/main.py` using `loguru`: JSON formatter with `session_id`, `turn_id`, `intent_classified`, `total_latency_ms` fields; log every turn at INFO, every tool call at DEBUG
- [ ] T087 [P] Standardize error envelope in `app/api/v1/chat.py`: convert `InvalidSessionIdError`, `PlaceToolError`, generic `Exception` into `{error: code, detail: msg}` per contracts/chat-api.md
- [ ] T088 [P] Test `tests/unit/test_trace_recorder.py`: simulate a 3-tool-call turn with mocked clock; assert TraceEntry has all required fields populated, `total_latency_ms ≈ sum(tool_latencies) + composer_overhead`, `final_status="ok"`, `fallback_used=false` for live legs
- [ ] T089 [P] Test `tests/unit/test_trace_eviction.py`: append 60 traces in a row; assert `len(session.traces) == 50` and the first 10 were dropped (FIFO)
- [ ] T090 [P] Test `tests/integration/test_trace_endpoint.py`: send 2 chat messages on a session, then GET `/chat/session/{id}/trace`; assert `count=2`, both entries present, fields well-formed; assert `composer_output` matches the actual responses returned to the user
- [ ] T091 [P] Test `tests/integration/test_concurrency.py` (SC-005): spin up 50 concurrent `POST /chat/message` calls with 50 distinct UUIDs each setting a different `dietary` preference; assert no preference leak across sessions and all responses returned within 15 s wall-clock
- [ ] T092 [P] Test `tests/integration/test_offtopic.py`: send "What's the price of AAPL stock?" — assert `intent_classified="CHAT_GENERAL"`, no tool calls dispatched (verify via mock), `reply_text` redirects user to travel topics
- [ ] T093 [P] Test `tests/contract/test_data_service_contract.py`: fetch `{DATA_SERVICE_URL}/openapi.json`, assert that the field set on Data Service `PlaceCandidateOut` is a superset of fields used by `Place` model in `app/session/models.py` (catches schema drift)
- [ ] T094 [P] Test `tests/contract/test_no_db_imports.py`: `import app` then walk `sys.modules`; assert no module name starts with `Chitogo_DataBase`, no `sqlalchemy` import, no `aiosqlite` import (decoupling guarantee)
- [ ] T095 Run `quickstart.md` end-to-end smoke against a real Data Service + real Google API: itinerary generation, replanning, trace inspection, route fallback (force by setting invalid Google key); document any gaps in `quickstart.md` Troubleshooting

**Checkpoint**: MVP demo-ready. All success criteria from spec.md (SC-001 through SC-007) have at least one corresponding test.

---

## Deferred / Later-Spec Tasks

These are intentionally NOT in the MVP scope — captured here so they don't get rediscovered later.

### Persistence and scale
- [ ] D001 Replace `InMemorySessionStore` with Redis-backed store
- [ ] D002 Add user accounts and cross-session preference history
- [ ] D003 Add per-user rate limiting on `POST /chat/message`
- [ ] D004 Add API key authentication on chat endpoints

### Replanning extensions
- [ ] D005 Add `Replanner.insert_stop(itinerary, after_index, new_place)` operation
- [ ] D006 Add `Replanner.remove_stop(itinerary, stop_index)` operation
- [ ] D007 Add `Replanner.reorder_stops(itinerary, new_order)` operation
- [ ] D008 Extend classifier to recognize `insert` / `remove` / `reorder` REPLAN sub-operations

### Itinerary depth
- [ ] D009 Multi-day itinerary support (currently MVP is single-day)
- [ ] D010 Per-venue overrides for `visit_duration_min` (requires Data Service field)
- [ ] D011 Time-of-day awareness in `place_search` (e.g., bias toward indoor venues during rain)

### Real-time signals
- [ ] D012 Weather-aware replanning (auto-suggest indoor swap when rain detected)
- [ ] D013 Crowd-density signal integration
- [ ] D014 Event/closure feed integration

### Agent and UX upgrades
- [ ] D015 Stream chat responses via Server-Sent Events
- [ ] D016 OpenTelemetry distributed tracing (replaces in-memory trace for prod)
- [ ] D017 LLM caching layer for classifier (cache repeated short messages)
- [ ] D018 A/B testing harness for classifier vs LLM-only baseline
- [ ] D019 Admin endpoint to dump all active sessions for debugging
- [ ] D020 Web-based trace viewer UI (currently JSON only)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundation)**: No dependencies — start here.
- **Phase 2 (Session)**: Depends on Phase 1 (uses `Settings`, app structure).
- **Phase 3 (Planner)**: Depends on Phase 1 (`llm/client.py`). Independent of Phase 2 except for session models in T011.
- **Phase 4 (Tool Adapters)**: Depends on Phase 1 only. Can be developed in parallel with Phases 2-3.
- **Phase 5 (Recommendation Flow)**: Depends on Phases 1-4 (composes everything together).
- **Phase 6 (Itinerary + Replanning)**: Depends on Phase 5 (extends composer + handler). US1 itinerary tasks (T063-T067, T072) and US3 replan tasks (T068-T071) can run in parallel within Phase 6.
- **Phase 7 (Observability)**: Depends on Phase 5 minimum; full coverage requires Phase 6 for trace recording on itinerary turns.

### User Story Mapping

- **US1 (Itinerary Generation, P1)**: T012-T013, T026, T063-T067, T072-T074, T077-T078, T080
- **US2 (Preference Extraction, P2)**: T017, T028-T029, T032-T033
- **US3 (Replanning, P2)**: T018, T027, T068-T071, T075-T076, T079
- **US4 (Explainable Responses, P3)**: T062 (and emerges naturally from `EXPLAIN` intent + trace endpoint without additional code)

### Parallel Opportunities

Within Phase 1: T004, T005, T007, T008, T009, T010 in parallel after T001-T003.
Within Phase 2: T016-T021 in parallel after T011-T015.
Within Phase 3: T030-T033 (tests) in parallel after T023-T029 (impl).
Within Phase 4: T036-T039 in parallel after T035; T045-T049 (tests) in parallel after impl.
Within Phase 5: T058-T062 in parallel after T056-T057.
Within Phase 6: itinerary chain T063-T067 || replan chain T068-T071; all tests T073-T080 in parallel after impl.
Within Phase 7: T085-T094 mostly parallel after T081-T084.

---

## Implementation Strategy

### MVP First (Hackathon Demo)

1. Phase 1 → Phase 2 → Phase 3 → Phase 4 (foundation through tools)
2. Phase 5 (recommendation flow visible in chat) — **first end-to-end demo**
3. Phase 6 (itinerary + replanning) — **second end-to-end demo, the hero flow**
4. Phase 7 (trace endpoint + concurrency + hardening) — **third demo: "show your work" panel**

### Incremental Delivery

Each phase ends in a runnable, testable state. The earliest user-visible milestone is the end of Phase 5 (chatting with the bot returns coherent recommendations). The hero demo is the end of Phase 6. The "wow" panel is Phase 7.

### Parallel Team Strategy

- **Dev A**: Phases 1-2 (foundation + session)
- **Dev B**: Phase 3 (planner + preferences) — can start as soon as Phase 1 is done
- **Dev C**: Phase 4 (tool adapters) — can start as soon as Phase 1 is done
- All hands converge on Phase 5; split US1 vs US3 work within Phase 6; reconverge on Phase 7.

---

## Notes

- Every task has an absolute file path (or test target) and a clear acceptance bar.
- All tests use mocked LLM and mocked HTTP transports unless explicitly an integration test against the real Data Service (T093, T095).
- The decoupling guarantee (Chat_Agent ↛ Chitogo_DataBase) is enforced by T094 contract test — never bypass it by importing Data Service models directly.
- Run `pytest --cov=app` after each phase to monitor coverage; aim for ≥ 80% on `app/orchestration/` and `app/tools/` before declaring the phase done.
- Commit at the end of each task or each parallel batch.
