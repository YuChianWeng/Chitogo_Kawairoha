# Phase 0 Research — Agent Orchestration Backend

**Date**: 2026-04-20
**Status**: All NEEDS CLARIFICATION items resolved (none remained after `/speckit.clarify`).

This document records the design decisions taken to resolve open questions in the Technical Context, the rationale for each, and rejected alternatives.

---

## R-001: LLM provider for the agent loop and intent classifier

- **Decision**: Use Anthropic Claude (the `anthropic` Python SDK) as the single LLM provider for both the agent loop and the LLM-fallback path of the Intent Classifier. Default model: `claude-sonnet-4-6`.
- **Rationale**:
  - Native tool-use API (`tools=[…]`, `tool_choice`, multi-turn tool result handoff) is the cleanest match for the LLM Agent Loop layer in this plan.
  - Same provider already in use elsewhere in this repo / for this hackathon track.
  - Tool schemas can be defined once in `tools/registry.py` and reused for both itinerary generation and replanning.
- **Alternatives considered**:
  - OpenAI function-calling: viable but requires a second SDK; no project-level reason to add it.
  - Local Llama / Ollama: rejected for the hackathon because tool-use latency and reliability are critical to demo quality.

---

## R-002: HTTP client for outbound calls (Data Service + Google Routing)

- **Decision**: Use `httpx.AsyncClient` (single shared instance per adapter, reused across requests).
- **Rationale**:
  - The Data Service itself uses FastAPI/Pydantic; aligning on httpx keeps async semantics consistent and simplifies test mocking via `httpx.MockTransport`.
  - Same-process async (no thread-pool boundary) is required for the agent loop to fan-out tool calls without blocking the event loop.
- **Alternatives considered**:
  - `requests` with `asyncio.to_thread`: simpler but adds thread overhead and breaks async cancellation semantics.
  - Anthropic Bedrock-style HTTP plug-in: overkill for two-endpoint integration.

---

## R-003: Google Routing API endpoint and parameter set

- **Decision**: Call the Google Maps Directions API via HTTP `GET https://maps.googleapis.com/maps/api/directions/json` with `mode=transit`, `origin=lat,lng`, `destination=lat,lng`, and (when supplied) `departure_time`. Parse `routes[0].legs[0].duration.value` (seconds) → `duration_min`. Mode-of-transit reported as `transit_method = "transit"`.
- **Rationale**:
  - Stable, documented, doesn't require billing-tier-specific routing-preference flags.
  - Minimal payload to parse; works with simple httpx client.
- **Alternatives considered**:
  - Google Maps Routes API (v2 `computeRoutes` POST): newer but requires field masks, more setup; not worth it for MVP.
  - GTFS local routing (e.g., OpenTripPlanner): rejected — adds infra; the spec explicitly calls for Google routing.

---

## R-004: Static-distance fallback formula for route failures

- **Decision**: Haversine great-circle distance between `(from_lat, from_lng)` and `(to_lat, to_lng)`, divided by an effective speed of **12 km/h** (mixed walking + short transit fallback assumption), rounded up to the nearest minute. The result is returned with `transit_method="estimated"` and `estimated=True`.
- **Rationale**:
  - 12 km/h is a published median for urban "walk + occasional bus/MRT" trips in dense city centers and yields conservative-but-not-absurd ETAs across Taipei (1 km ≈ 5 minutes; matches Taipei MRT walk-to-station + ride patterns for short hops).
  - Calculation is deterministic, dependency-free, and instant — preserves demo latency budget.
- **Alternatives considered**:
  - Pure walking speed (5 km/h): too pessimistic for cross-district hops (would inflate a 5 km leg to 60 min).
  - Cached historical Google response: rejected — adds storage; falls outside MVP scope.

---

## R-005: Intent Classifier strategy (rules vs LLM vs hybrid)

- **Decision**: **Rules-first with LLM fallback.** Try regex/keyword rules per intent (high precision, low recall by design). If no rule matches with confidence, fall back to a single Claude Haiku call returning a strict-JSON `{intent, slots}` answer. Cap LLM-fallback latency at 1 s.
- **Rationale**:
  - Keeps the deterministic gating real for the 80 % of obvious cases (e.g., starts with "plan", contains "replace stop N", starts with "why").
  - LLM fallback handles long-tail phrasings without hand-coding regex forever.
  - Explicit two-tier design keeps the hybrid clarification (Q3) intact.
- **Alternatives considered**:
  - Pure LLM classifier: simpler code but adds latency and cost on every turn.
  - Pure regex classifier: brittle; misclassifies polite or indirect phrasings ("could you suggest…?").

---

## R-006: Anchoring `arrival_time` in itineraries

- **Decision**: Default itinerary start time is **10:00 Asia/Taipei** unless the user states a start time (extracted as `time_window.start` by `PreferenceExtractor`). All `arrival_time` strings are local Taipei time (`HH:MM`). Times are computed by `ItineraryBuilder` by sequentially adding `visit_duration_min` and the next `Leg.duration_min`.
- **Rationale**:
  - Most travel chat starts mid-morning; 10:00 default avoids weird-looking 09:01 starts.
  - All venues are in Taipei; storing a single timezone simplifies render.
- **Alternatives considered**:
  - Storing UTC ISO timestamps: more "correct" but adds frontend conversion burden and clutters the demo.

---

## R-007: Visit-duration heuristic per category

- **Decision**: `ItineraryBuilder` uses category-based defaults, overridable by LLM if it suggests a different value:
  - `attraction`: 60 min
  - `food`: 75 min
  - `shopping`: 45 min
  - `nightlife`: 90 min
  - `lodging` / `transport` / `other`: 30 min
- **Rationale**: Removes a class of decisions from the LLM (deterministic + testable), but LLM can still override when it has a reason ("Taipei 101 observatory needs 90 min").
- **Alternatives considered**:
  - LLM-decides everything: less consistent across runs and harder to test.
  - Per-venue field in the Data Service: out of scope for this feature; would need a Data Service change.

---

## R-008: Session store data structure and TTL sweep

- **Decision**: `dict[UUID, Session]` guarded by a single `asyncio.Lock`. Background asyncio task runs every 60 s and deletes any session with `last_active_at` older than 30 minutes. Read/write paths call `touch()` to update `last_active_at` to `datetime.utcnow()`.
- **Rationale**:
  - Hackathon-scale (≤ 100 sessions) — no need for a more sophisticated data structure.
  - Single lock is fine since per-turn work is dominated by external I/O (LLM + tool calls), not in-memory contention.
  - Dedicated sweeper avoids per-request expiration checks scattered across the codebase.
- **Alternatives considered**:
  - LRU with max size: adds complexity without addressing the actual TTL requirement.
  - Per-key locks: premature optimization for the expected concurrency.

---

## R-009: Trace-entry storage bound

- **Decision**: Cap `Session.traces` at the most recent **50 entries** (FIFO eviction).
- **Rationale**: Demo only ever inspects the last few turns; 50 is generous and bounds memory at ~500 KB per session worst case.
- **Alternatives considered**:
  - Unbounded: leaks memory under prolonged sessions.
  - Cap at 10: too small for a multi-iteration demo flow.

---

## R-010: Place-tool ↔ Data Service schema mapping

- **Decision**: The `Place` model in `app/session/models.py` mirrors the Data Service `PlaceCandidateOut` field-by-field (`id`, `display_name`, `internal_category`, `latitude`, `longitude`, `district`, `primary_type`, `rating`, `budget_level`, `indoor`, etc.). The mapping is performed in `PlaceToolAdapter` via a Pydantic model deserialized from the HTTP response.
- **Rationale**:
  - 1:1 mapping prevents semantic drift; a contract test (`test_data_service_contract.py`) pins the schema by validating against `/openapi.json` from the live Data Service.
  - Keeps the adapter thin — no field renaming or business logic.
- **Alternatives considered**:
  - Custom internal Place schema with translation layer: more control but doubles maintenance for zero gain at this scale.

---

## R-011: Tool exposure per intent

- **Decision**: Tool registry filters tools by intent before passing them to the LLM:

  | Intent | Tools exposed |
  |---|---|
  | `GENERATE_ITINERARY` | `place_search`, `place_recommend`, `place_nearby`, `place_batch`, `place_categories`, `route_estimate` |
  | `REPLAN` | `place_search`, `place_nearby`, `place_batch`, `route_estimate` |
  | `EXPLAIN` | (none — pure LLM with session context) |
  | `CHAT_GENERAL` | `place_search` (only — for conversational lookup) |

- **Rationale**: Implements the spec's clarified hybrid contract (deterministic gating, LLM-driven within scope). Prevents an `EXPLAIN` turn from accidentally re-fetching everything.
- **Alternatives considered**:
  - All tools always: violates the gating intent.
  - One tool per intent: too restrictive for `GENERATE_ITINERARY`.

---

## R-012: Bilingual handling (English + Traditional Chinese)

- **Decision**: Detect language by simple Unicode-block check on the user message; pass the detected language as a system-prompt hint (`"User language: zh-TW"`) to the LLM for both the agent loop and the response composer. No translation of venue names or categories — the LLM produces the reply in the user's language directly.
- **Rationale**:
  - Avoids a second translation call per turn.
  - Anthropic models handle Traditional Chinese well; minimal prompting suffices.
- **Alternatives considered**:
  - Per-message LLM language detection: redundant, adds latency.
  - Translating Data Service responses: unnecessary — venue display names from Google are already in the appropriate locale.

---

## Open issues (for future post-MVP specs)

- Replanning operations beyond `replace` (`insert`, `remove`, `reorder`) — design noted, deferred.
- Streaming chat responses (SSE) for better perceived latency — deferred.
- Persistent session store (Redis) for multi-instance deployment — deferred.
- Per-user rate limiting — deferred (no auth yet).
