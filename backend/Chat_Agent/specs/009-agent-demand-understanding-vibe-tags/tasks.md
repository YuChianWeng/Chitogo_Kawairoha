---
description: "Task list for 009-agent-demand-understanding-vibe-tags"
---

# Tasks: Constraint-Aware Demand Understanding and Database-Backed Vibe Tags

**Input**: Design documents from `specs/009-agent-demand-understanding-vibe-tags/`  
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/chat-api.md, contracts/data-service-vibe-tags.md, contracts/tools.md

**Tests**: Tests are required for each observed failure mode: natural replan target resolution, replacement constraints, cache filtering, database-known vibe tags, mixed-category itineraries, preference merge hygiene, and afternoon time preservation.

**Organization**: Tasks are organized by implementation phase. `[P]` means the task can be done in parallel with other tasks that touch different files.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel
- **[USn]**: Maps to user stories in spec.md

---

## Phase 1: Data Service Vibe Tag Catalog

**Acceptance target**: Chat_Agent can call a Data Service endpoint that returns known normalized `vibe_tags` scoped by optional district/category/type filters.

- [x] T001 [P] [US2] Add `VibeTagItem` and `VibeTagsResponse` schemas in `backend/Chitogo_DataBase/app/schemas/retrieval.py`
- [x] T002 [US2] Add `backend/Chitogo_DataBase/app/services/vibe_tags.py` with `list_vibe_tags(db, district=None, internal_category=None, primary_type=None, limit=50)`
- [x] T003 [US2] Implement PostgreSQL JSONB aggregation over `Place.vibe_tags`, returning distinct tag counts sorted by `place_count DESC`
- [x] T004 [US2] Add `GET /api/v1/places/vibe-tags` in `backend/Chitogo_DataBase/app/routers/places.py`
- [x] T005 [P] [US2] Add DataBase tests for unfiltered tag catalog, district-scoped catalog, category-scoped catalog, and empty catalog
- [x] T006 [P] [US2] Update DataBase README/API notes to document `/places/vibe-tags`

## Phase 2: Chat_Agent Tool Support

**Acceptance target**: Chat_Agent has a safe tool/adapter path for known vibe tags and can forward selected tags to search.

- [x] T007 [P] [US2] Extend `backend/Chat_Agent/app/tools/models.py` with `VibeTagItem` and `VibeTagListResult`
- [x] T008 [US2] Add `PlaceToolAdapter.get_vibe_tags()` in `backend/Chat_Agent/app/tools/place_adapter.py` calling `/api/v1/places/vibe-tags`
- [x] T009 [US2] Register `place_vibe_tags` in `backend/Chat_Agent/app/tools/registry.py`
- [x] T010 [P] [US2] Add adapter tests for success, empty, malformed payload, timeout, and scoped query params
- [x] T011 [P] [US2] Confirm existing `search_places(vibe_tags=[...])` emits repeated `vibe_tag` params and add regression coverage if missing

## Phase 3: TurnIntentFrame Models and Validation

**Acceptance target**: Current-turn executable constraints are represented separately from stable session preferences.

- [ ] T012 [P] [US1] Add `backend/Chat_Agent/app/orchestration/turn_frame.py` with `TurnIntentFrame`, `PlaceConstraint`, `TargetReference`, `VibeTagSelection`, `CategoryMixItem`, and `CandidateMatchDecision`
- [ ] T013 [US1] Add validators ensuring replan frames have operation + valid target reference when required
- [ ] T014 [US2] Add validation that selected vibe tags are a subset of known tags when a catalog is available
- [ ] T015 [US4] Add stable-vs-turn-specific merge helpers so `TurnIntentFrame.stable_preference_delta` is the only part eligible for session preference merge
- [ ] T016 [P] [US1] Add unit tests for valid/invalid TurnIntentFrame combinations
- [ ] T017 [P] [US2] Add unit tests that unknown LLM-proposed vibe tags are rejected and recorded

## Phase 4: Structured Extraction Pipeline

**Acceptance target**: Regex fast path handles obvious cases, while LLM structured extraction handles broader natural phrasing and is validated before execution.

- [ ] T018 [P] [US1] Extend ordinal extraction in `backend/Chat_Agent/app/orchestration/slots.py` for `第二個`, `第二間`, `第二家`, and spacing variants
- [ ] T019 [US1] Add regex fast-path extraction for simple replan constraints such as `換成公園`, `換成景點`, `換成日式餐廳`
- [ ] T020 [US1] Add LLM structured TurnIntentFrame extraction prompt in `turn_frame.py`
- [ ] T021 [US2] Add known-tag selection prompt that receives only Data Service tags and returns selected tags + confidence
- [ ] T022 [US1] Add validation fallback: low confidence or invalid target reference sets `needs_clarification=True`
- [ ] T023 [P] [US1] Add tests for "可以把第二個換成景點嗎", "第三站換成公園", "last stop", and ambiguous target references
- [ ] T024 [P] [US2] Add tests for "浪漫日式餐廳" selecting `romantic` only when catalog contains it

## Phase 5: Replan Cache Filtering and Refetch

**Acceptance target**: Replan replacement never uses a cached candidate that violates the current replacement constraint.

- [ ] T025 [US1] Add `candidate_matches_constraint()` helper, returning `CandidateMatchDecision`
- [ ] T026 [US1] Update `MessageHandler._pick_cached_replan_candidate` to require constraint matching
- [ ] T027 [US1] Update replan flow to refetch through AgentLoop when cache has no matching candidates
- [ ] T028 [US1] Pass `replacement_constraint` into AgentLoop for replan retrieval
- [ ] T029 [P] [US1] Add tests where cache contains only food and user asks for park; assert fresh search occurs
- [ ] T030 [P] [US1] Add tests where cache contains matching attraction; assert cache can be reused
- [ ] T031 [P] [US1] Add trace tests for cache match/mismatch decisions

## Phase 6: Preference Merge Hygiene

**Acceptance target**: New explicit turn constraints do not pollute later turns, and null/omitted fields do not clear stable session preferences.

- [ ] T032 [US4] Update `merge_preferences()` in `backend/Chat_Agent/app/session/manager.py` so omitted fields are preserved and explicit `None` does not clear stable fields by default
- [ ] T033 [US4] Ensure replacement/search-only constraints are not merged into session `interest_tags`
- [ ] T034 [US4] Add explicit correction handling for stable fields, e.g. changing district or transport
- [ ] T035 [P] [US4] Add tests for old "park" request not influencing later "Japanese restaurant" request
- [ ] T036 [P] [US4] Add tests for LLM payload with `district: null` preserving existing district
- [ ] T037 [P] [US4] Add tests for explicit district correction overwriting old district

## Phase 7: Vibe-Aware Retrieval

**Acceptance target**: Vibe-aware discovery and itinerary generation use known tags in Data Service queries.

- [ ] T038 [US2] Update AgentLoop planned-call normalization to accept `vibe_tags`, `min_mentions`, and social sort values after validation
- [ ] T039 [US2] Add context-aware known-tag lookup before place retrieval when the message contains vibe language or LLM frame requests vibe
- [ ] T040 [US2] Use `place_search` fallback instead of `place_recommend` when recommend cannot support vibe filters
- [ ] T041 [US2] Add relaxation behavior for empty vibe-tag results: drop secondary tags, then fallback to social sort only
- [ ] T042 [P] [US2] Add tests for `vibe_tag=romantic` search params on romantic restaurant request
- [ ] T043 [P] [US2] Add tests for missing catalog and unavailable catalog fallback behavior

## Phase 8: Mixed Itinerary Retrieval and Selection

**Acceptance target**: "Play and eat" requests produce a category-diverse itinerary when data exists.

- [ ] T044 [US3] Add category-mix extraction for `有玩有吃`, `景點加餐廳`, `逛街吃飯`, and LLM structured equivalents
- [ ] T045 [US3] Update AgentLoop to run one retrieval per `CategoryMixItem`
- [ ] T046 [US3] Preserve source category metadata on returned candidates
- [ ] T047 [US3] Update ItineraryBuilder selection to enforce category diversity before falling back to highest-ranked candidates
- [ ] T048 [US3] Add category-mix relaxation message when one category has no candidates
- [ ] T049 [P] [US3] Add tests for `有玩有吃` returning both `attraction` and `food`
- [ ] T050 [P] [US3] Add tests for `逛街吃飯` returning `shopping` and `food`
- [ ] T051 [P] [US3] Add tests for one missing category producing a relaxation note

## Phase 9: Discovery and Time Window Fixes

**Acceptance target**: Direct place-finding requests enter discovery, and afternoon hints do not fall back to morning itinerary starts.

- [ ] T052 [US5] Expand discovery detection to include `幫我找`, `找一個`, `找一間`, `找一家`, and LLM-frame discovery signals
- [ ] T053 [US5] Ensure discovery requests for specific place candidates do not trigger itinerary-only missing-field clarification
- [ ] T054 [US4] Ensure "下午", "下午出發", and "afternoon" map to an afternoon time window in stable preference extraction or turn frame
- [ ] T055 [US4] Replace hardcoded itinerary default start time with settings/default and current turn time-window fallback
- [ ] T056 [P] [US5] Add tests for "幫我找一個好玩的公園" using place search
- [ ] T057 [P] [US4] Add tests for afternoon start time at or after 13:00

## Phase 10: Trace, Documentation, and Regression Suite

**Acceptance target**: Failures are inspectable through trace, and all observed conversation failures have regression coverage.

- [ ] T058 [US1] Add trace step `turn_frame.validate` with sanitized frame details
- [ ] T059 [US2] Add trace step `vibe_tags.select` with known count, selected tags, and rejected tags
- [ ] T060 [US1] Add trace step `replan.cache_candidate_filter`
- [ ] T061 [US3] Add trace detail for category-mix retrieval and relaxation
- [ ] T062 [P] Update `backend/Chat_Agent/README.md` current limitations/behavior notes after implementation
- [ ] T063 Run targeted Chat_Agent tests: `tests/test_agent_loop.py`, `tests/test_message_handler.py`, `tests/test_replanner.py`, `tests/test_preference_extractor.py`
- [ ] T064 Run DataBase retrieval/social tests affected by vibe tags
- [ ] T065 Run full relevant backend test suites and record results in implementation notes

## Deferred Tasks

- [ ] D001 Use embedding similarity for named-stop references such as "the ramen place"
- [ ] D002 Add OR semantics for vibe tags by running multiple searches and merging results
- [ ] D003 Add route-aware ordering optimization for mixed itineraries
- [ ] D004 Add persistent tag catalog caching with TTL in Chat_Agent
- [ ] D005 Add frontend UI hints showing when constraints were relaxed

## Dependencies and Execution Order

1. Phase 1 and Phase 2 establish the known-tag contract.
2. Phase 3 and Phase 4 introduce TurnIntentFrame extraction.
3. Phase 5 fixes the most severe replan bug.
4. Phase 6 prevents old requests from polluting new requests.
5. Phase 7 enables real vibe-aware retrieval.
6. Phase 8 adds mixed itinerary quality.
7. Phase 9 fixes discovery/time regressions.
8. Phase 10 hardens trace and documentation.

The highest-priority safe cut is Phases 3-6: even before full vibe ranking, the assistant must stop replacing parks/attractions with restaurants.
