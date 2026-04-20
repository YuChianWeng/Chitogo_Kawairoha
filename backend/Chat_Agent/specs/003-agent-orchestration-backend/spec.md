# Feature Specification: Agent Orchestration Backend

**Feature Branch**: `003-agent-orchestration-backend`  
**Created**: 2026-04-20  
**Status**: Draft  
**Input**: User description: "Chat-oriented orchestration backend for Taipei travel AI assistant — decoupled from data service, supporting session memory, preference extraction, tool routing, itinerary generation, replanning, and explainable responses."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conversational Itinerary Generation (Priority: P1)

A traveler opens a chat interface and describes what they want to do in Taipei ("I want to spend one day exploring night markets and temples, I prefer walking and transit, budget is moderate"). The assistant asks clarifying questions if needed, then produces a full-day itinerary with time slots, venue names, and transit directions between stops.

**Why this priority**: This is the core value proposition of the product. Without end-to-end itinerary generation from a natural chat request, nothing else matters.

**Independent Test**: Can be tested by sending a freeform travel intent message and verifying a structured, ordered itinerary with venues and transit legs is returned — without any pre-seeded itinerary data.

**Acceptance Scenarios**:

1. **Given** a new chat session, **When** the user sends a message describing their interests and available time, **Then** the assistant returns a day-plan with at least 3 venues ordered by visit sequence, each annotated with estimated visit duration and transit time to the next stop.
2. **Given** the assistant has returned an itinerary, **When** the user asks "why did you pick this route?", **Then** the assistant explains each venue choice in terms of the user's stated preferences.
3. **Given** a vague request ("show me something interesting"), **When** the user sends it, **Then** the assistant asks at least one clarifying question before generating the itinerary.

---

### User Story 2 - Preference Extraction Across a Session (Priority: P2)

During a multi-turn conversation, the user mentions preferences ("I don't like crowded places", "I'm vegetarian", "I only have until 5pm"). The assistant retains these across the session and factors them into every itinerary it produces, without requiring the user to repeat themselves.

**Why this priority**: Preference memory is what distinguishes a smart assistant from a simple search tool. It enables progressive personalization within a session.

**Independent Test**: Can be tested by sending preferences in turn 1 and a new itinerary request in turn 3, verifying the output respects the earlier preferences without the user restating them.

**Acceptance Scenarios**:

1. **Given** the user stated "I'm vegetarian" in turn 1, **When** the user requests a food-focused itinerary in turn 4, **Then** all recommended venues are suitable for vegetarians.
2. **Given** the user said "I don't want to travel far", **When** generating a multi-stop itinerary, **Then** the total estimated transit time is minimized and each leg is flagged.
3. **Given** the user corrects a preference ("actually, I'm fine with crowds at night"), **When** the next itinerary is generated, **Then** the updated preference overrides the earlier one.

---

### User Story 3 - Dynamic Replanning on Request (Priority: P2)

During a conversation, the user asks to change the itinerary ("skip the museum, add something near Ximending instead" or "it started raining, suggest indoor activities"). The assistant regenerates the affected portion of the itinerary while keeping unchanged stops intact.

**Why this priority**: Travel plans change constantly. Replanning from scratch would frustrate users. Targeted replanning preserves the work done and respects what the user already approved.

**Independent Test**: Can be tested by requesting a change to one stop in a previously generated itinerary and verifying that only the modified portion is regenerated while the rest is preserved.

**Acceptance Scenarios**:

1. **Given** a 4-stop itinerary, **When** the user says "replace stop 2 with something else", **Then** stops 1, 3, and 4 remain, and a new stop 2 is suggested with updated transit legs on either side.
2. **Given** the user requests an indoor-only plan due to weather, **When** the assistant replans, **Then** all newly suggested venues are categorized as indoor.
3. **Given** a time constraint changes ("I now only have 3 hours"), **When** the user informs the assistant, **Then** the itinerary is condensed to fit within the new window.

---

### User Story 4 - Explainable Responses (Priority: P3)

The user can ask why a particular venue or route was recommended, and the assistant provides a plain-language explanation referencing the user's own preferences and constraints.

**Why this priority**: Explainability builds trust. Users are more likely to follow a recommended itinerary when they understand the reasoning behind it.

**Independent Test**: Can be tested by generating an itinerary and asking "why this order?" — the assistant should cite at least one user preference and one logistical factor (e.g., transit time, opening hours).

**Acceptance Scenarios**:

1. **Given** an itinerary has been generated, **When** the user asks "why did you include X?", **Then** the assistant references at least one matching preference or constraint from the session.
2. **Given** the assistant suggested a transit route, **When** the user asks "why this route?", **Then** the assistant explains the transit method, estimated time, and why alternatives were not chosen.

---

### Edge Cases

- What happens when no venues match the user's preferences and constraints (e.g., vegetarian + late night + budget < 200 TWD)?
- How does the system handle conflicting preferences within the same session (e.g., "I like quiet places" followed by "take me to a night market")?
- What happens when transit routing returns no path between two venues (e.g., remote location, service outage)?
- How does the assistant behave if the user sends a completely off-topic message (e.g., asking about stock prices)?
- What happens when the user's session expires or is reset mid-itinerary?
- How does the system respond when external POI or routing services are temporarily unavailable?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain a per-session conversation history that persists across multiple turns within the same session. Each session is identified by a client-generated UUID passed with every request. The server holds session state in memory and expires it after 30 minutes of inactivity.
- **FR-002**: System MUST extract and store user preferences from natural language messages (e.g., dietary restrictions, activity types, mobility constraints, budget range, time availability) without explicit structured input.
- **FR-003**: System MUST route requests through a three-layer architecture: (1) a deterministic **Intent Classifier** maps each user message to a named intent category (e.g., GENERATE_ITINERARY, REPLAN, EXPLAIN, CHAT_GENERAL); (2) an **LLM Agent Loop** receives the classified intent and executes the appropriate tool calls (POI retrieval, transit routing) in a reasoning loop without hard-coded venue or route logic; (3) a **Response Composer** formats the agent's tool outputs into the final structured itinerary JSON plus narrative string.
- **FR-004**: System MUST compose multi-stop itineraries by combining POI results with transit time estimates, ordered by logical visit sequence.
- **FR-005**: System MUST support targeted replanning: when the user requests a change to part of an itinerary, only the affected stops and connecting transit legs are regenerated.
- **FR-006**: System MUST produce explainable responses: when asked, the assistant must cite specific user preferences and constraints that drove each recommendation.
- **FR-007**: System MUST remain decoupled from the data service — all venue and route data must be retrieved through defined tool interfaces, not embedded in agent logic.
- **FR-008**: System MUST handle graceful degradation when a tool call fails. Specifically, when transit routing fails for one or more legs, the itinerary MUST still be returned with the affected legs replaced by a static distance-based time estimate and marked `estimated: true`. The narrative MUST note which legs use estimated rather than live transit data. If POI retrieval fails entirely, the system MUST return a user-facing error message rather than an empty or silent response.
- **FR-009**: System MUST support session isolation — one user's session must not influence another user's session.
- **FR-011**: System MUST record a per-turn trace entry in session memory for every request. Each trace entry MUST contain: `turn_id`, `intent_classified`, `tool_calls` (list of `{name, input, output, latency_ms}`), `composer_output`, and `total_latency_ms`. Trace entries MUST be accessible via a dedicated read-only endpoint for debugging and demo purposes.
- **FR-010**: System MUST accept and respond to conversational messages in both English and Traditional Chinese.

### Key Entities

- **Session**: A bounded conversation context identified by a client-generated UUID. Contains message history, extracted preferences, and the current active itinerary state. Created implicitly on first use of a new UUID; expires after 30 minutes of inactivity; held in server memory for v1.
- **Preference**: A structured or semi-structured record of a user's stated constraints and interests (e.g., activity type, dietary need, budget, mobility, time window), extracted from conversation turns.
- **Itinerary**: An ordered list of stops plus a top-level narrative string. Each **Stop** carries: `stop_index`, `venue_id`, `venue_name`, `category`, `arrival_time`, `visit_duration_min`, `lat`, `lng`. Each **Transit Leg** carries: `from_stop` (index), `to_stop` (index), `transit_method`, `duration_min`. The top-level `narrative` field is a human-readable summary of the full plan suitable for rendering directly in the chat bubble.
- **Intent**: A named category assigned by the deterministic classifier to each user message. MVP intent set: `GENERATE_ITINERARY` (build a new day plan), `REPLAN` (modify part of an existing itinerary), `EXPLAIN` (justify a recommendation), `CHAT_GENERAL` (handle off-topic or greeting messages without tool calls).
- **Trace Entry**: A per-turn observability record stored in session memory. Shape: `{turn_id, intent_classified, tool_calls: [{name, input, output, latency_ms}], composer_output, total_latency_ms}`. Exposes the full agent reasoning chain for debugging and demo purposes.
- **Tool Call**: A discrete invocation of an external capability (POI retrieval or transit routing) with inputs and outputs recorded in the turn's Trace Entry.
- **Venue Reference**: A pointer to a place record in the data service, containing at minimum an identifier, name, category, and location — no itinerary logic stored in the reference.
- **Transit Leg**: A travel segment between two venues carrying: `from_stop`, `to_stop`, `transit_method`, `duration_min`, and `estimated` (boolean — `true` when live routing was unavailable and a static distance-based fallback was used instead).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can receive a complete, multi-stop day itinerary within 10 seconds of submitting a travel intent message.
- **SC-002**: Preferences stated in any prior turn are reflected in all subsequent itinerary suggestions within the same session, with zero repetition prompts needed from the user.
- **SC-003**: When a user requests a partial replanning change, the unmodified stops in the itinerary are preserved in 100% of cases.
- **SC-004**: The assistant provides an explanation referencing at least one user preference or constraint in response to any "why" question about the itinerary.
- **SC-005**: The system handles at least 50 concurrent chat sessions without degradation in response quality or session isolation.
- **SC-006**: Tool call failures (POI or routing) result in a user-facing fallback message rather than a silent error or system crash in 100% of cases.
- **SC-007**: 90% of itinerary generation attempts successfully complete without requiring the user to restate preferences already given in the session.

## Clarifications

### Session 2026-04-20

- Q: What is the session identity model — how is a session created and when does it end? → A: Client generates and owns a UUID session ID before first message; server holds state for that ID with a 30-minute inactivity TTL.
- Q: What is the itinerary response structure? → A: Structured JSON with typed stops `{stop_index, venue_id, venue_name, category, arrival_time, visit_duration_min, lat, lng}` and transit legs `{from_stop, to_stop, transit_method, duration_min}`, plus a top-level `narrative` string for the chat bubble.
- Q: Who decides which tools to call and in what order? → A: Hybrid — deterministic Intent Classifier maps messages to named intent categories (GENERATE_ITINERARY, REPLAN, EXPLAIN, CHAT_GENERAL); LLM Agent Loop handles tool calls within the classified scope; Response Composer formats final structured JSON + narrative output.
- Q: When transit routing fails for one or more legs, what should the itinerary contain? → A: Return the itinerary with affected legs replaced by static distance-based time estimates and marked `estimated: true`; narrative notes which legs use estimated data.
- Q: What session-level trace data must be recorded per request? → A: Per-turn trace in session memory: `{turn_id, intent_classified, tool_calls: [{name, input, output, latency_ms}], composer_output, total_latency_ms}`, accessible via a read-only endpoint.

## Assumptions

- The existing Taipei POI retrieval API is available as a callable tool interface and returns structured venue data including name, category, location, and operating hours.
- Google public transit routing is accessible as a callable tool interface and returns estimated travel time and method between two geographic points.
- Session state does not need to persist across server restarts for v1 — in-memory session storage is sufficient. Sessions are identified by client-generated UUIDs and expire after 30 minutes of inactivity.
- Multi-language support is limited to English and Traditional Chinese for v1.
- The agent backend does not serve the frontend directly; it exposes a conversational API that a separate frontend layer consumes.
- Budget categories (low / moderate / high) are defined by the data service and used as filter inputs to the POI tool — the agent backend does not define price ranges.
- Operating hours enforcement is handled by the POI tool; the agent does not independently validate venue availability.
- The agent does not store personal user data beyond the active session — no user accounts or cross-session history are required for v1.
