# Feature Specification: Constraint-Aware Demand Understanding and Database-Backed Vibe Tags

**Feature Branch**: `009-agent-demand-understanding-vibe-tags`  
**Created**: 2026-04-24  
**Status**: Draft  
**Input**: User-observed chat failures where the assistant repeatedly returned restaurants, failed to interpret replan wording such as "second one", ignored "park/attraction" replacement requests, let old session interests pollute new requests, and did not use database-known `vibe_tags` for requests such as romantic restaurants.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Natural Replanning With Replacement Constraints (Priority: P1)

A traveler has an existing itinerary and asks to modify one stop using natural phrasing, such as "can you change the second one to an attraction?" or "change the third stop to a park." The assistant identifies the intended stop, extracts the replacement constraints, and only uses a replacement place that satisfies those constraints.

**Why this priority**: The current system can replace a stop with an unrelated cached restaurant even when the user explicitly asks for an attraction or park. This breaks trust in the core itinerary editing workflow.

**Independent Test**: Generate a restaurant-heavy itinerary, then ask to replace the second stop with an attraction. Verify the updated second stop is not a food venue and that unchanged stops remain preserved.

**Acceptance Scenarios**:

1. **Given** a 4-stop itinerary whose cached candidates are all food venues, **When** the user says "第三站換成公園", **Then** the assistant must not use a cached food venue and must query for an attraction/park replacement.
2. **Given** a 4-stop itinerary, **When** the user says "可以把第二個換成景點嗎", **Then** the assistant resolves "第二個" to stop index 1 and applies an attraction replacement or asks a targeted clarification if no valid replacement can be found.
3. **Given** a replan request with ambiguous target wording and low confidence, **When** the assistant cannot validate a single target stop, **Then** it asks which stop to change instead of silently changing a guessed stop.

---

### User Story 2 - Vibe-Aware Search From Database-Known Tags (Priority: P1)

A traveler asks for a place with a vibe, such as "romantic Japanese restaurant", "quiet cafe", or "fun park." The assistant obtains the current known `vibe_tags` from the Place Data Service and asks the LLM to choose only from those tags, rather than inventing unsupported labels.

**Why this priority**: Vibe vocabulary comes from social ingestion and changes with the data. Hardcoding a small list in Chat_Agent will drift from the database and miss existing tags.

**Independent Test**: Mock the Data Service known tag list to include `romantic` and `scenic`. Send "幫我找一間浪漫一點的日式餐廳" and verify the agent searches for `primary_type=japanese_restaurant` with `vibe_tag=romantic`.

**Acceptance Scenarios**:

1. **Given** the Data Service reports `romantic` as a known tag for food venues, **When** the user asks for a romantic restaurant, **Then** the assistant includes `romantic` in the place query.
2. **Given** the Data Service does not report a tag matching the user's requested vibe, **When** the user asks for that vibe, **Then** the assistant does not invent a tag and instead falls back to a broader category/type search with a trace warning.
3. **Given** multiple known tags are available, **When** the user asks for a compound vibe such as "quiet and scenic", **Then** the assistant may select multiple known tags only if they are present in the Data Service response.

---

### User Story 3 - Mixed Itineraries for "Play and Eat" Requests (Priority: P1)

A traveler requests an itinerary that includes more than one kind of activity, such as "有玩有吃" or "attractions and food." The assistant plans with an explicit category mix and returns an itinerary containing both activity and food stops.

**Why this priority**: The current AgentLoop often chooses one category and the ItineraryBuilder takes the first N candidates, causing "play and eat" requests to return all restaurants.

**Independent Test**: Send "幫我排一個有玩有吃的行程下午從大安區出發" and verify the returned itinerary contains at least one `food` stop and at least one `attraction` stop, with an afternoon start time.

**Acceptance Scenarios**:

1. **Given** the user asks for "有玩有吃", **When** an itinerary is generated, **Then** the result includes both `attraction` and `food` stops when matching data exists.
2. **Given** one requested category has no matches, **When** the assistant relaxes constraints, **Then** the response mentions the relaxation and still avoids presenting a single-category plan as if it satisfied the original request.
3. **Given** the user asks for "逛街吃飯", **When** an itinerary is generated, **Then** the assistant uses a category mix containing `shopping` and `food`.

---

### User Story 4 - Turn-Specific Constraints Without Session Pollution (Priority: P2)

A traveler changes their mind across turns. New explicit place-type requests should override old turn-specific interests, while stable preferences such as origin, district, language, and transport can persist.

**Why this priority**: The current merge behavior accumulates `interest_tags`, so a later Japanese restaurant request can still be influenced by an older park request.

**Independent Test**: Ask for a park, then ask for a romantic Japanese restaurant and provide origin/time in the next turn. Verify the final plan/search honors the restaurant request instead of using the old park constraint.

**Acceptance Scenarios**:

1. **Given** the previous turn requested a park, **When** the next explicit request is "日式餐廳浪漫一點", **Then** the current turn search constraint is restaurant/Japanese, not park.
2. **Given** the LLM extraction returns omitted fields or explicit JSON nulls for stable preferences, **When** preferences are merged, **Then** omitted/null fields do not erase existing origin, district, or time window unless the user clearly requested clearing or changing them.
3. **Given** a replan request contains replacement-only constraints, **When** it succeeds, **Then** those constraints do not globally overwrite the user's long-lived session preferences unless the user clearly states a global preference change.

---

### User Story 5 - Discovery Requests Enter Place Search Reliably (Priority: P2)

A traveler asks a direct place-finding question such as "幫我找一個好玩的公園." The assistant recognizes the request as discovery/search, not general chat, and returns place candidates or a useful no-results response.

**Why this priority**: A travel assistant that replies with a generic capability message to a direct place-finding request feels broken.

**Independent Test**: Send "幫我找一個好玩的公園" in a fresh session and verify a place-search tool is used with attraction/park constraints.

**Acceptance Scenarios**:

1. **Given** a fresh session, **When** the user says "幫我找一個好玩的公園", **Then** the assistant calls a place retrieval tool instead of returning general chat help.
2. **Given** the user asks for a specific place type without origin/time, **When** the intent is discovery rather than itinerary generation, **Then** the assistant can return candidates without asking for itinerary-only missing fields.

## Edge Cases

- What if the user says "the one after the cafe" and multiple cafe stops exist?
- What if the user asks for "romantic" but no known Data Service tag maps to that meaning?
- What if repeated `vibe_tag` filters are too strict and return no results?
- What if a category mix asks for food + attraction but only food exists in the requested district?
- What if the LLM proposes a `primary_type` or `vibe_tag` not present in the allowed vocabulary?
- What if the user uses ordinal wording not covered by the regex fast path?
- What if new turn constraints conflict with long-lived session preferences?
- What if the Data Service known-tag endpoint is unavailable?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create a per-turn structured demand frame before tool execution. The frame MUST capture intent, stable preference deltas, turn-specific place constraints, category mix, replan operation, target reference, and confidence.
- **FR-002**: Regex/parser logic MUST be treated as a high-confidence fast path only. If regex cannot produce a validated frame, the system MUST call an LLM structured extractor and validate the result before executing any mutation.
- **FR-003**: System MUST support natural target references for replanning beyond "第 N 站", including "第二個", "第二間", "第二家", "last stop", and LLM-resolved references. Unsupported or ambiguous references MUST trigger clarification.
- **FR-004**: Replan requests MUST carry replacement constraints when the user specifies them, including `internal_category`, `primary_type`, `keyword`, and `vibe_tags`.
- **FR-005**: Cached replacement candidates MUST be filtered against the replacement constraints. A cached candidate that does not satisfy category/type/vibe requirements MUST NOT be used.
- **FR-006**: Chat_Agent MUST obtain known `vibe_tags` from the Place Data Service through a tool/adapter before asking the LLM to select vibe tags.
- **FR-007**: LLM-selected `vibe_tags` MUST be a subset of the known tags returned by the Data Service. Unknown tags MUST be rejected and recorded as a validation warning.
- **FR-008**: Place search execution MUST pass selected `vibe_tags` to the Data Service using repeated `vibe_tag` query parameters. The system SHOULD use social sort fields such as `sentiment_desc`, `trend_score_desc`, or `mention_count_desc` when the selected vibe implies ranking rather than strict filtering.
- **FR-009**: Place recommendation execution MUST support vibe-aware ranking either by extending the Data Service recommend endpoint or by using search as the fallback when `vibe_tags` are present.
- **FR-010**: Itinerary generation MUST support a `category_mix` and must attempt one retrieval per requested category when a mixed request is detected.
- **FR-011**: Itinerary selection MUST preserve category diversity for mixed requests when matching candidates exist.
- **FR-012**: Preference merge semantics MUST distinguish stable session preferences from turn-specific constraints. Omitted/null fields MUST NOT erase stable preferences by default.
- **FR-013**: Time-window extraction MUST consistently map "下午" and "afternoon" to an afternoon start window. ItineraryBuilder MUST not fall back to a morning default when an afternoon hint is present in the current or retained context.
- **FR-014**: Discovery requests for specific place types MUST not be blocked by itinerary-only missing-field clarification.
- **FR-015**: Trace output MUST include the validated turn demand frame, selected known vibe tags, rejected unknown tags, cache-match decisions, and constraint relaxations.
- **FR-016**: The system MUST ask a targeted clarification when no validated frame can safely identify the requested operation, target stop, or required replacement constraints.

### Key Entities

- **TurnIntentFrame**: A per-turn structured representation of the user's current request. It is the executable contract between natural-language understanding and tool orchestration.
- **PlaceConstraint**: A structured set of retrieval filters for a search, recommendation, or replacement candidate. Includes category/type/keyword/vibe/social ranking fields.
- **TargetReference**: A validated reference to an itinerary stop, such as a zero-based index, ordinal phrase, relative phrase, or named stop.
- **VibeTagCatalog**: The Data Service-provided list of known tags available for selection. It is scoped by optional district/category/type filters.
- **VibeTagSelection**: LLM-selected vibe tags plus confidence, rejected tags, and fallback strategy.
- **CategoryMix**: An ordered or weighted set of desired internal categories for itinerary generation.
- **CandidateMatchDecision**: A traceable decision explaining whether a cached candidate can satisfy a constraint.

## Success Criteria *(mandatory)*

- **SC-001**: 95% of supported replan examples in the regression suite resolve the correct target stop or ask clarification; zero examples silently mutate the wrong stop.
- **SC-002**: When a user requests an attraction/park replacement and cached candidates are all food venues, 100% of successful replans fetch a new non-food candidate.
- **SC-003**: For mocked known tags containing `romantic`, romantic restaurant requests include `vibe_tag=romantic` in the retrieval path in 100% of tests.
- **SC-004**: For mocked known tags that do not contain a requested vibe, the system rejects unknown tags and still returns a broader result or asks a useful clarification; it never sends invented tags.
- **SC-005**: Mixed "play and eat" requests return at least one food stop and one attraction stop when both categories have candidates.
- **SC-006**: Stable session fields such as origin, district, language, transport, and time window are not cleared by omitted/null LLM extraction fields.
- **SC-007**: "Afternoon" requests produce itinerary first-stop arrival times at or after 13:00 unless the user explicitly specifies another time.

## Assumptions

- The Place Data Service remains the source of truth for available `vibe_tags`.
- Some Data Service work may be required to expose a tag catalog and extend recommendation scoring; those tasks are captured in this Chat_Agent spec because the Chat_Agent behavior depends on them.
- Hardcoded phrase mappings may still exist as guardrails, but they must not be the only path for understanding arbitrary user wording.
- The public chat API can remain backward-compatible; most changes are internal orchestration, trace detail, and Data Service contract changes.
