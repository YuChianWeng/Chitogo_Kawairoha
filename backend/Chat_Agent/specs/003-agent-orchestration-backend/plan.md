# Implementation Plan: Agent Orchestration Backend

**Branch**: `003-agent-orchestration-backend` | **Date**: 2026-04-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/003-agent-orchestration-backend/spec.md`

## Summary

Build a chat-oriented orchestration backend for the Taipei travel AI assistant. The service exposes a small chat API to the frontend and produces explainable, multi-stop itineraries by orchestrating two external capabilities as tools: (1) the existing Place Data Service retrieval APIs (`search`, `recommend`, `batch`, `nearby`, `stats`, `categories`) and (2) Google public-transit routing for dynamic transit estimation.

Architectural approach is a **hybrid 3-layer** pipeline per turn:

1. **Deterministic Intent Classifier** — maps each incoming user message to one of `GENERATE_ITINERARY`, `REPLAN`, `EXPLAIN`, `CHAT_GENERAL`. Determines the allowed tool scope.
2. **LLM Agent Loop** — given the classified intent, the LLM reasons over registered tools (place + route adapters) and chooses which to call, in what order, with what arguments. No hard-coded venue or itinerary logic.
3. **Response Composer** — a thin formatting layer that packages tool outputs into the structured itinerary JSON (stops, legs, narrative, routing_status) and writes the per-turn trace to session memory.

Sessions are in-memory with a 30-minute inactivity TTL, identified by client-generated UUIDs. The Place Data Service is never queried directly; all venue access goes through a `PlaceToolAdapter` that calls the Data Service HTTP API. Route fallback uses a static distance-based estimate when Google routing fails, marking affected legs `estimated: true` and setting `routing_status` to `partial_fallback`.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI 0.111, Pydantic v2, httpx (for Data Service + Google Maps calls), Anthropic SDK (Claude for the agent loop), uvicorn
**Storage**: In-memory session store (dict + asyncio lock) for v1; no DB for the agent backend itself
**Testing**: pytest, pytest-asyncio, httpx mock transport for tool adapter tests
**Target Platform**: Linux server (containerizable; same runtime as the Data Service)
**Project Type**: Web service (single-project layout under `backend/Chat_Agent/`)
**Performance Goals**: p95 chat-turn latency ≤ 10 s end-to-end (per SC-001); ≥ 50 concurrent sessions (per SC-005)
**Constraints**: No direct DB access for place data — must call Data Service HTTP API; no cross-session persistence; no user accounts
**Scale/Scope**: Hackathon MVP — single-instance deployment, ≤ 100 active sessions, 4 named intents, 2 tool adapters

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution at `.specify/memory/constitution.md` is currently the unfilled template — no ratified principles are defined yet. **No gates to evaluate**. The spec-level constraints (decoupling from Data Service, no hard-coded place/itinerary logic, in-memory v1, MVP scope) are treated as the binding contract for this feature.

**Status**: Pass (vacuous — no constitution rules to violate).

## Project Structure

### Documentation (this feature)

```text
specs/003-agent-orchestration-backend/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── chat-api.md      # Frontend-facing HTTP contract
│   └── tools.md         # Internal tool adapter interfaces
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
backend/Chat_Agent/
├── app/
│   ├── main.py                       # FastAPI entrypoint, router wiring, startup
│   ├── config.py                     # Settings (Data Service URL, Google API key, LLM key, TTL)
│   ├── api/
│   │   └── v1/
│   │       ├── chat.py               # POST /chat/message, GET /chat/session/{id}, GET /chat/session/{id}/trace
│   │       └── health.py
│   ├── session/
│   │   ├── store.py                  # In-memory store + TTL sweeper (asyncio task)
│   │   ├── manager.py                # Session create/get/touch/expire API
│   │   └── models.py                 # Session, Turn, Preference, Itinerary, TraceEntry pydantic models
│   ├── orchestration/
│   │   ├── handler.py                # MessageHandler — top-level per-turn pipeline
│   │   ├── classifier.py             # Deterministic Intent Classifier (rules + lightweight LLM fallback)
│   │   ├── preferences.py            # PreferenceExtractor — LLM call to merge preferences into session state
│   │   ├── agent_loop.py             # LLM Agent Loop — Claude tool-use loop with bounded iterations
│   │   ├── composer.py               # Response Composer — structures tool outputs into final itinerary JSON
│   │   ├── itinerary.py              # ItineraryBuilder — assembles stops/legs from candidate places + route results
│   │   ├── replanner.py              # ReplanningEngine — partial regeneration (replace/insert/remove stop)
│   │   └── trace.py                  # TraceRecorder — appends per-turn trace entries
│   ├── tools/
│   │   ├── registry.py               # ToolRegistry — exposes tool schemas to the LLM
│   │   ├── place_adapter.py          # PlaceToolAdapter — wraps Data Service HTTP API
│   │   └── route_adapter.py          # RouteToolAdapter — wraps Google transit API + static fallback
│   └── llm/
│       └── client.py                 # Anthropic client wrapper (single shared instance)
└── tests/
    ├── unit/
    │   ├── test_session_store.py
    │   ├── test_classifier.py
    │   ├── test_preferences.py
    │   ├── test_composer.py
    │   ├── test_itinerary.py
    │   ├── test_replanner.py
    │   └── test_trace.py
    ├── integration/
    │   ├── test_place_adapter.py     # Against mocked httpx transport
    │   ├── test_route_adapter.py     # Against mocked httpx transport, including failure modes
    │   ├── test_chat_endpoint.py     # End-to-end FastAPI TestClient for /chat/message
    │   └── test_session_lifecycle.py # TTL expiry, isolation
    └── contract/
        └── test_data_service_contract.py # Pinned schema check against Data Service /openapi.json
```

**Structure Decision**: Single-project Python web service under `backend/Chat_Agent/app/`, mirroring the Data Service layout (`backend/Chitogo_DataBase/app/`). The frontend is a separate concern and lives in its own root-level `frontend/`. The agent backend depends on the Data Service over HTTP only — it never imports from `Chitogo_DataBase`.

---

## Architecture

### High-Level Diagram

```text
┌────────────────┐     ┌─────────────────────────────────┐     ┌─────────────────────┐
│   Frontend     │ ──▶ │  Chat_Agent (this service)      │ ──▶ │ Place Data Service  │
│  (Vue/Vite)    │     │                                 │     │ (existing FastAPI)  │
│                │     │  • Intent Classifier            │     └─────────────────────┘
│                │     │  • LLM Agent Loop (Claude)      │
│                │ ◀── │  • Response Composer            │ ──▶ ┌─────────────────────┐
└────────────────┘     │  • Session Store (in-memory)    │     │ Google Maps Transit │
                       │  • Trace Recorder               │     │ Routing API         │
                       └─────────────────────────────────┘     └─────────────────────┘
```

### Boundaries

| Boundary | Contract |
|---|---|
| **Frontend ↔ Chat_Agent** | JSON HTTP API (chat/session/trace endpoints). Frontend owns `session_id` UUID. |
| **Chat_Agent ↔ Place Data Service** | `PlaceToolAdapter` calls `GET/POST /api/v1/places/*`. Adapter owns retries, timeouts, and schema deserialization. The agent loop sees the adapter as a tool, never the raw HTTP client. |
| **Chat_Agent ↔ Google Routing** | `RouteToolAdapter` calls Google Maps Transit Directions API. Adapter owns fallback logic and timeout. Returns `RouteResult` with `estimated: bool`. |
| **Internal: Classifier ↔ Agent Loop** | Classifier returns an `Intent` enum + extracted slot values; agent loop reads only those, not the raw user message verbatim — enforces deterministic gating. |
| **Internal: Agent Loop ↔ Composer** | Agent loop returns a list of accumulated tool outputs and a free-form summary string; composer transforms into the canonical itinerary JSON. |

### Decoupling Guarantees

- The agent backend has **zero imports** from `backend/Chitogo_DataBase/`. Verified by a contract test that imports the agent package and asserts the import set excludes `Chitogo_DataBase.*`.
- No SQL or SQLAlchemy in the agent backend. Verified by ruff/grep check in CI.

---

## Main Modules and Responsibilities

| Module | Responsibility |
|---|---|
| `session/store.py` | Owns the `dict[session_id, Session]` mapping. Provides `get`, `put`, `touch`, `delete`. Async-safe with a single `asyncio.Lock`. Background sweeper expires entries idle > 30 min. |
| `session/manager.py` | Public façade: `get_or_create(session_id) -> Session`. Validates UUID format. Calls `touch` on access. |
| `orchestration/handler.py` | Top-level pipeline per turn: load session → classify → extract preferences → invoke agent loop → compose response → record trace → return. |
| `orchestration/classifier.py` | Deterministic intent classifier. Uses regex/keyword rules for high-confidence cases ("plan a day" → GENERATE_ITINERARY, "replace stop" → REPLAN, "why" → EXPLAIN). Falls back to a single short LLM classification call when ambiguous. Returns `(Intent, slot_dict)`. |
| `orchestration/preferences.py` | Single LLM call: given new user message + current preferences, return updated preference dict. Idempotent merge — corrections overwrite. |
| `tools/registry.py` | Holds tool definitions (name, description, JSON schema). Exposed to the LLM agent loop via Anthropic tool-use format. Allowed tool subset is filtered by intent (e.g., `CHAT_GENERAL` exposes no tools). |
| `tools/place_adapter.py` | Async httpx client for Data Service. Methods map 1:1 to retrieval endpoints: `search`, `recommend`, `nearby`, `batch`, `categories`, `stats`. Handles retries (1 retry, 2 s timeout each). |
| `tools/route_adapter.py` | Async httpx client for Google Maps Transit Directions API. Returns `RouteResult{transit_method, duration_min, estimated}`. On failure (timeout, non-2xx, no route): falls back to haversine-distance × 12 km/h walking speed and sets `estimated: true`. |
| `orchestration/agent_loop.py` | Drives the Anthropic tool-use loop. Bounded to `max_iterations=6` per turn. Records every tool call into the in-progress trace entry. |
| `orchestration/itinerary.py` | Pure logic: given a list of candidate places + per-leg route results + arrival-time anchor, produces ordered stops with `arrival_time`, `visit_duration_min`, and connecting legs. No external calls. |
| `orchestration/replanner.py` | Pure logic: given an existing itinerary + a replan instruction (replace/insert/remove `stop_index`), returns a delta to apply. Calls back into `itinerary.py` to recompute affected segments. |
| `orchestration/composer.py` | Assembles final response: `{reply_text, itinerary, routing_status, session_id, turn_id}`. Computes `routing_status` from the leg `estimated` flags. |
| `orchestration/trace.py` | Builds per-turn `TraceEntry`, appends to `session.traces`. Bounded to last 50 entries per session. |

---

## Data Model Additions

All data lives in-memory inside the session object. Pydantic v2 models, no DB.

```text
Session
├── session_id: UUID                     # client-supplied
├── created_at: datetime
├── last_active_at: datetime             # touched per turn; drives TTL
├── preferences: Preferences             # extracted, merged across turns
├── turns: list[Turn]                    # full conversation history
├── current_itinerary: Itinerary | None  # the latest produced plan
├── candidate_places: list[Place]        # cached from last retrieval call (for replanning)
└── traces: list[TraceEntry]             # bounded to 50 entries

Turn
├── turn_id: UUID
├── role: "user" | "assistant"
├── content: str
└── created_at: datetime

Preferences (all optional)
├── activity_types: list[str]            # e.g., ["temple", "night_market"]
├── dietary: list[str]                   # e.g., ["vegetarian"]
├── budget_level: int | None             # 0-4 mapped to Data Service budget_level
├── mobility: str | None                 # "walking" | "transit" | "any"
├── time_window: TimeWindow | None       # {start: "10:00", end: "17:00"}
├── districts: list[str]                 # preferred Taipei districts
├── language: "en" | "zh-TW"
└── crowd_tolerance: str | None          # "low" | "moderate" | "high"

Itinerary
├── itinerary_id: UUID
├── summary: str                         # short headline, e.g., "1-day Ximending + Longshan Temple"
├── total_duration_min: int
├── stops: list[Stop]                    # ordered by stop_index
├── legs: list[Leg]                      # len == len(stops) - 1
└── created_at: datetime

Stop
├── stop_index: int                      # 0-based, dense
├── venue_id: int                        # Data Service Place.id
├── venue_name: str
├── category: str                        # internal_category from Data Service
├── arrival_time: str                    # "HH:MM" local Taipei time
├── visit_duration_min: int
├── lat: float
└── lng: float

Leg
├── from_stop: int
├── to_stop: int
├── transit_method: str                  # "transit" | "walking" | "estimated"
├── duration_min: int
└── estimated: bool                      # true if route fallback was used

TraceEntry
├── turn_id: UUID
├── intent_classified: str               # one of the 4 intents
├── tool_calls: list[ToolCallRecord]     # {name, input, output, latency_ms}
├── composer_output: dict                # the response payload
├── total_latency_ms: int
├── fallback_used: bool                  # true if any leg used the static fallback
└── final_status: str                    # "ok" | "partial_fallback" | "error"
```

Full Pydantic-shaped definitions live in [data-model.md](./data-model.md).

---

## Frontend API Surface

Base path: `/api/v1/chat/`. All endpoints are JSON-in / JSON-out. Authentication is out of scope for v1 (hackathon).

### `POST /api/v1/chat/message`

Send a user message and receive an assistant reply (with itinerary if relevant).

**Request**:
```json
{
  "session_id": "8f3c…uuid",
  "message": "I want to spend the afternoon around Ximending, vegetarian please."
}
```

**Response**:
```json
{
  "session_id": "8f3c…uuid",
  "turn_id": "1a2b…uuid",
  "reply_text": "Here's a 4-stop afternoon plan around Ximending…",
  "itinerary": {
    "itinerary_id": "9d…",
    "summary": "Afternoon in Ximending — vegetarian-friendly",
    "total_duration_min": 240,
    "stops": [ /* Stop objects */ ],
    "legs":  [ /* Leg objects */ ]
  },
  "routing_status": "full",
  "intent_classified": "GENERATE_ITINERARY"
}
```

`itinerary` is `null` for `EXPLAIN` and `CHAT_GENERAL` turns. Session is created implicitly on first use of an unknown UUID.

### `GET /api/v1/chat/session/{session_id}`

Fetch full session state for debugging and resuming UI.

**Response**: `Session` payload (sans traces by default; pass `?include=traces` to include them).

### `GET /api/v1/chat/session/{session_id}/trace`

Fetch the per-turn trace history. Used by the demo "show your work" panel.

**Response**: `{traces: [TraceEntry, …], count: int}`.

### `DELETE /api/v1/chat/session/{session_id}`

Explicit teardown (optional — TTL cleanup also handles it).

### `GET /api/v1/health`

Liveness probe. Returns `{status: "ok", data_service: "reachable" | "degraded"}`.

Full request/response schemas live in [contracts/chat-api.md](./contracts/chat-api.md).

---

## Internal Tool / Service Interfaces

### `PlaceToolAdapter` (Python interface)

```python
class PlaceToolAdapter(Protocol):
    async def search(self, params: PlaceSearchParams) -> list[Place]: ...
    async def recommend(self, params: RecommendParams) -> list[Place]: ...
    async def nearby(self, params: NearbyParams) -> list[Place]: ...
    async def batch(self, place_ids: list[int]) -> list[Place]: ...
    async def categories(self) -> list[Category]: ...
    async def stats(self) -> PlaceStats: ...
```

`Place` is the agent-internal representation, mapped 1:1 from Data Service `PlaceCandidateOut`. The adapter swallows transport errors and raises a single `PlaceToolError` so the agent loop can react uniformly.

### `RouteToolAdapter`

```python
class RouteToolAdapter(Protocol):
    async def estimate_leg(
        self,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float,
        depart_at: datetime | None = None,
    ) -> RouteResult: ...

class RouteResult(BaseModel):
    transit_method: str       # "transit" | "walking" | "estimated"
    duration_min: int
    estimated: bool           # True iff fallback was used
```

The adapter NEVER raises on routing failure; it returns `RouteResult(estimated=True, …)`. This keeps the agent loop's control flow simple.

### Planner / Composer Boundary

- The **agent loop** never writes to `Session.current_itinerary` or `Session.traces` directly. It returns a `LoopResult` containing tool call records and a free-form text reasoning string.
- The **composer** is the only writer to `Session.current_itinerary` and `Session.traces`. It takes the `LoopResult`, calls `ItineraryBuilder`/`Replanner` as needed, computes `routing_status`, and produces the API response.

Full tool schemas and adapter contracts live in [contracts/tools.md](./contracts/tools.md).

---

## Request Flows

### A) Recommendation Request (no itinerary, just suggestions)

User: *"What are some good vegetarian restaurants near Ximending?"*

1. `MessageHandler` loads session by UUID; touches `last_active_at`.
2. `IntentClassifier` returns `CHAT_GENERAL` (no itinerary verb detected) — but slot extraction picks up `category=food`, `district=Ximending`.
3. `PreferenceExtractor` updates `preferences.dietary = ["vegetarian"]`, `preferences.districts = ["Ximending"]`.
4. `AgentLoop` runs with the `place_search` tool exposed (and `route_estimate` excluded since intent is not itinerary-bound). LLM calls `place_search(internal_category=food, district=Ximending, indoor=True)`.
5. `PlaceToolAdapter` → Data Service `GET /api/v1/places/search` → returns 8 candidates.
6. LLM returns a short list with names and rationale.
7. `Composer` returns `{reply_text, itinerary: null, routing_status: "full", intent_classified: "CHAT_GENERAL"}`.
8. `TraceRecorder` writes the entry.

### B) Itinerary Planning Request

User: *"Plan me a 1-day Ximending + Longshan Temple trip, vegetarian, transit only."*

1. Load + touch session.
2. Classifier → `GENERATE_ITINERARY` with slots `{districts: [Ximending, Wanhua], duration: "1-day", dietary: vegetarian, mobility: transit}`.
3. PreferenceExtractor merges into session preferences.
4. AgentLoop exposes `[place_search, place_recommend, place_nearby, route_estimate]`. LLM iterates:
   - `place_recommend(districts=["Ximending","Wanhua"], internal_category=attraction, limit=5)`
   - `place_recommend(districts=["Ximending","Wanhua"], internal_category=food, limit=5)`
   - Picks 4 venues; calls `route_estimate` for each consecutive pair.
5. AgentLoop returns `LoopResult` with selected venue IDs, route results, and a narrative.
6. Composer → `ItineraryBuilder` produces `Stop[]` and `Leg[]`, sets `arrival_time` anchored to user's stated start time (default 10:00). Computes `routing_status = "full"` (all legs live).
7. Stored as `session.current_itinerary`. Trace recorded. Response returned.

### C) Replanning Request

User: *"Replace stop 2 with something else, ideally a temple."*

1. Load session; current itinerary present.
2. Classifier → `REPLAN` with slots `{stop_index: 2, replacement_hint: "temple"}`.
3. AgentLoop exposes `[place_search, place_nearby, route_estimate]`. LLM:
   - `place_nearby(lat=stop1.lat, lng=stop1.lng, radius_m=2000, internal_category=attraction, primary_type=hindu_temple)` (LLM picks the type from its general knowledge; data-service category mapping enforces actual filtering).
   - Picks one new venue.
   - `route_estimate(stop1 → new)` and `route_estimate(new → stop3)` to recompute the two affected legs.
4. Composer → `Replanner.replace(itinerary, stop_index=2, new_stop, new_legs)`. Stops 0, 1, 3, ... and unaffected legs preserved verbatim (per SC-003).
5. Updated itinerary returned with `routing_status` recomputed.

### D) Route Fallback Scenario

During flow B, the route adapter times out on the leg `stop_2 → stop_3`.

1. `RouteToolAdapter.estimate_leg` catches `httpx.TimeoutException`, computes haversine distance, divides by 12 km/h walking speed, returns `RouteResult(transit_method="estimated", duration_min=N, estimated=True)`. NO exception raised.
2. AgentLoop continues normally — it doesn't even know fallback occurred.
3. Composer iterates legs; if any `estimated=True`, sets `routing_status = "partial_fallback"`. Adds a sentence to `reply_text`: *"Note: transit time between stop 2 and stop 3 is an approximate walking estimate."*
4. Trace records `fallback_used=True` and `final_status="partial_fallback"`.

If ALL legs fall back (e.g., Google API down): `routing_status = "failed"` (full degradation, but itinerary still returned).

---

## Validation and Fallback Rules

| Condition | Behavior |
|---|---|
| `session_id` is missing or not a valid UUID | 400 with `{error: "invalid_session_id"}` |
| Required user info missing for itinerary (e.g., user said "plan something" with no time/area) | Classifier emits `GENERATE_ITINERARY` but with `needs_clarification=True`. Composer returns a clarifying question instead of calling tools — covers spec acceptance scenario 1.3. |
| Place retrieval returns 0 candidates | LLM is informed via tool result; relaxes filters once (e.g., drops `min_rating`); if still 0, composer returns a graceful "no matches" reply with the relaxed query echoed back. |
| Place retrieval returns < 3 candidates and intent is `GENERATE_ITINERARY` | LLM may retry with broader filters or fewer constraints once. If still insufficient, returns the partial set with a note. |
| Route API fails for one leg | Per-leg fallback; `routing_status = "partial_fallback"`. Itinerary returned. |
| Route API fails for ALL legs | All legs `estimated=True`; `routing_status = "failed"`. Itinerary still returned. |
| LLM agent loop exceeds `max_iterations=6` | Loop terminates; composer returns whatever was accumulated with a note. Trace marks `final_status="error"` only if zero useful tool output was gathered. |
| Replan instruction references a stop_index out of range | Composer returns `{reply_text: "Stop N doesn't exist in your current itinerary…"}`, no itinerary mutation. |
| Off-topic message (e.g., stock price question) | Classifier emits `CHAT_GENERAL`; agent loop responds without tool calls; redirects user to travel topics. |
| Session expired between turns | Server transparently creates a fresh session with the same UUID. Response includes a `session_recreated: true` flag so frontend can clear stale local state. |

---

## Testing Strategy

| Area | Approach |
|---|---|
| Session lifecycle / TTL | Unit: fast-clock TTL test. Integration: send turn → wait sweep tick → confirm cleared. |
| Session isolation | Integration: 2 concurrent UUIDs, each setting a different `dietary` preference; assert no leak. |
| Preference extraction | Unit: feed canned messages, assert merged Preferences object. Use a mock LLM client. |
| Pre-classifier behavior | Unit: ~30 message → expected-intent fixtures covering each intent + ambiguous cases that hit LLM fallback. |
| Tool routing (intent-scoped tool exposure) | Unit: assert that for `EXPLAIN` intent, the registry exposes no place/route tools; for `CHAT_GENERAL`, only `place_search`; etc. |
| Itinerary JSON shape | Contract test: validate every produced response against a Pydantic model derived from the spec. |
| Route fallback | Unit: route adapter with httpx mock returning timeout/500 → assert `estimated=True` and `routing_status` propagation. |
| Replanning preservation (SC-003) | Property test: for a 4-stop itinerary, replace each stop in turn; assert stops at non-target indices are byte-for-byte preserved. |
| Trace recording | Unit: simulate a full pipeline turn; assert TraceEntry fields populated and bounded list size. |
| Place adapter ↔ Data Service contract | Contract test: hit the Data Service `/openapi.json` and assert our adapter's request/response models match the spec field names and types. |
| End-to-end happy path | Integration: spin up the FastAPI TestClient with mocked LLM + mocked Data Service + mocked Google API; send a 3-turn conversation; assert preferences carry over and itinerary is well-formed. |

---

## Implementation Phases

### Phase 1 — Foundation
- Scaffold `backend/Chat_Agent/app/` with FastAPI app, config, health endpoint.
- `requirements.txt` with FastAPI, httpx, anthropic, pydantic v2, pytest.
- Env settings: `DATA_SERVICE_URL`, `GOOGLE_MAPS_API_KEY`, `ANTHROPIC_API_KEY`, `SESSION_TTL_MIN=30`.

### Phase 2 — Session and State
- Pydantic models for `Session`, `Turn`, `Preferences`, `Itinerary`, `Stop`, `Leg`, `TraceEntry`.
- In-memory `SessionStore` with asyncio lock.
- Background TTL sweeper (asyncio task, runs every 60 s).
- `SessionManager` façade with UUID validation.
- Unit tests for store + lifecycle + isolation.

### Phase 3 — Planner and Preference Extraction
- `IntentClassifier` (rules + LLM fallback) with intent enum and slot output.
- `PreferenceExtractor` LLM call with merge logic.
- Unit tests with canned message fixtures.

### Phase 4 — Tool Adapters
- `PlaceToolAdapter` with all 6 retrieval methods + `PlaceToolError`.
- `RouteToolAdapter` with Google Maps Transit call + haversine fallback.
- `ToolRegistry` exposing schemas in Anthropic tool-use format.
- Adapter unit/integration tests with httpx mock transport.

### Phase 5 — Recommendation Flow (CHAT_GENERAL + suggestion-only paths)
- Wire `MessageHandler` for non-itinerary intents.
- Implement `AgentLoop` with bounded iterations.
- Implement minimal `Composer` for non-itinerary responses.
- Implement `POST /chat/message` endpoint.
- Integration tests for recommendation flow.

### Phase 6 — Itinerary and Replanning
- `ItineraryBuilder` (pure logic, full unit coverage).
- `Replanner` with replace / insert / remove operations.
- Extend `Composer` for itinerary responses with `routing_status` calculation.
- Integration tests for `GENERATE_ITINERARY` and `REPLAN` flows.

### Phase 7 — Observability and Hardening
- `TraceRecorder` + `GET /chat/session/{id}/trace` endpoint.
- Structured logging via `loguru` or stdlib logging with JSON formatter.
- Concurrency stress test (50 simultaneous sessions).
- Error envelope standardization.
- README + quickstart for the demo.

---

## MVP vs Deferred Work

### MVP (must ship for the hackathon demo)

- All 4 intents (`GENERATE_ITINERARY`, `REPLAN`, `EXPLAIN`, `CHAT_GENERAL`) working end-to-end.
- All 6 Data Service retrieval endpoints wrapped in `PlaceToolAdapter`.
- Google Maps Transit Routing tool with haversine fallback and `routing_status` field.
- In-memory session store with 30-min TTL.
- Per-turn trace + `GET /trace` endpoint (key demo feature).
- Replanning: `replace_stop_at_index` operation (most common use case).
- Bilingual support: pass user language as a system prompt hint to the LLM; frontend already provides input text.
- One-clearing-question behavior for vague itinerary requests.

### Deferred (post-hackathon)

- Persistent session store (Redis or Postgres).
- User accounts and cross-session preference history.
- Replanning operations beyond replace: `insert_stop_at`, `remove_stop_at`, `reorder_stops`.
- Streaming responses (SSE) for the chat endpoint.
- Authentication/authorization on the chat API.
- Multi-day itinerary support (current MVP is single-day).
- Real-time data integrations (weather, crowd density, event feeds).
- Distributed tracing (OpenTelemetry) — replaced by in-memory trace for MVP.
- Caching layer in front of `PlaceToolAdapter` (Data Service is local; not needed yet).
- Rate limiting / quota management on the chat endpoint.
- A/B testing of classifier prompts.

---

## Complexity Tracking

> No constitution-level violations to justify (constitution is unfilled). Hybrid 3-layer pipeline (classifier → agent loop → composer) is justified by the explicit clarification in the spec; alternatives (pure deterministic router, pure LLM agent) were rejected because the former hard-codes intent logic and the latter has no controlled gating.

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Hybrid Intent Classifier + LLM Agent Loop | Prevents arbitrary tool use on off-topic messages; supports demo "show your work" trace | Pure LLM agent: harder to bound; pure rule router: hard-codes itinerary logic (violates FR-007) |
| In-memory session store with manual TTL sweeper | Hackathon timeline; no Redis dependency | Redis: extra infra; bare dict without TTL: leaks memory under demo load |
| Static distance fallback for route failures | Required by FR-008 + spec clarification; keeps demo resilient | Returning an error: blocks the demo when Google is flaky (common at conferences) |
