# Implementation Plan: Constraint-Aware Demand Understanding and Database-Backed Vibe Tags

**Branch**: `009-agent-demand-understanding-vibe-tags` | **Date**: 2026-04-24 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/009-agent-demand-understanding-vibe-tags/spec.md`

## Summary

Upgrade Chat_Agent from regex-heavy, session-preference-driven behavior to a per-turn structured demand pipeline. Each user turn produces a validated `TurnIntentFrame` before tool calls or itinerary mutation. Regex remains as a fast path, but ambiguous wording is handled by an LLM structured extractor whose output is validated against deterministic vocabularies and current session state.

The key design changes are:

1. **Turn frame before execution**: separate the current turn's executable constraints from long-lived session preferences.
2. **Constraint-aware replanning**: replacement candidates must match requested category/type/vibe constraints; cached candidates are no longer reused blindly.
3. **Database-backed vibe tags**: Chat_Agent queries a Data Service tag catalog and allows the LLM to choose only from known tags.
4. **Mixed itinerary planning**: requests such as "有玩有吃" produce explicit category mixes and multi-query retrieval plans.
5. **Safer preference merge**: omitted/null extraction fields do not erase stable session state, and turn-specific constraints do not pollute future turns.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, Pydantic v2, httpx, configured LLM provider through existing `LLMClient`  
**Storage**: Existing in-memory Chat_Agent session store; no new Chat_Agent database  
**External Dependency**: Place Data Service must provide known `vibe_tags` and either vibe-aware recommend or search fallback  
**Testing**: pytest with existing fake LLM and mocked adapters  
**Target Platform**: Existing backend service layout under `backend/Chat_Agent/`  
**Compatibility**: Public chat response should remain backward-compatible where possible; trace detail may be extended

## Constitution Check

The repository does not contain an active ratified constitution. Existing architectural constraints from the current agent backend remain binding:

- Chat_Agent must not import or query the Data Service database directly.
- Place data access must go through tool adapters.
- LLM outputs must be validated before mutating session or itinerary state.
- Existing tests for current chat, route, trace, and adapter behavior must continue passing.

**Status**: Pass.

## Project Structure

### Documentation (this feature)

```text
specs/009-agent-demand-understanding-vibe-tags/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── chat-api.md
│   ├── data-service-vibe-tags.md
│   └── tools.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Areas Expected To Change

```text
backend/Chat_Agent/app/
├── orchestration/
│   ├── classifier.py          # keep intent classification, feed frame extraction
│   ├── preferences.py         # safer merge inputs, stable vs turn-specific fields
│   ├── slots.py               # target reference helpers / ordinal fast path
│   └── turn_frame.py          # new structured demand frame extraction and validation
├── chat/
│   ├── message_handler.py     # use TurnIntentFrame for dispatch and replan constraints
│   ├── loop.py                # execute category mixes and vibe-aware retrieval
│   ├── replanner.py           # parse/apply replacement constraints
│   ├── itinerary_builder.py   # preserve category diversity in selection
│   └── trace_recorder.py      # include frame and validation decisions in trace
├── session/
│   ├── models.py              # add stable preference fields if needed
│   └── manager.py             # safer merge semantics
└── tools/
    ├── models.py              # tag catalog / social fields
    ├── place_adapter.py       # known vibe tag endpoint and vibe-aware params
    └── registry.py            # register new tag-catalog tool

backend/Chitogo_DataBase/app/
├── routers/places.py          # dependent endpoint: /places/vibe-tags
├── schemas/retrieval.py       # tag catalog schemas and recommend extensions
└── services/vibe_tags.py      # aggregate known tags from places.vibe_tags
```

## Architecture

### Current Problem Flow

```text
User message
  ├─ classifier intent
  ├─ preference extractor merges into session
  └─ handler chooses flow
       ├─ replan may reuse any cached candidate not already used
       └─ generate uses single-category candidate list
```

This permits the following failures:

- Replacement constraints are lost before candidate selection.
- Cached food candidates are reused for attraction requests.
- Old interest tags accumulate and affect future unrelated turns.
- Vibe requests are treated as free text rather than Data Service filters.

### New Flow

```text
User message
  ├─ load session
  ├─ classify high-level intent
  ├─ build TurnIntentFrame
  │    ├─ regex fast path when high confidence
  │    ├─ LLM structured extraction when needed
  │    ├─ fetch known vibe tags when vibe may matter
  │    └─ deterministic validation against session + vocabularies
  ├─ merge only stable preference deltas
  ├─ execute flow from validated frame
  │    ├─ discovery/search uses search_constraint
  │    ├─ generate uses category_mix + search_constraint
  │    └─ replan uses target_reference + replacement_constraint
  └─ compose response + trace frame decisions
```

### Key Boundaries

| Boundary | Contract |
|---|---|
| User message to `TurnIntentFrame` | LLM may propose structure; backend validates and may reject fields. |
| `TurnIntentFrame` to AgentLoop | AgentLoop receives structured constraints, not just merged session preferences. |
| Chat_Agent to Data Service tags | Place adapter fetches known tags through `/api/v1/places/vibe-tags`; LLM cannot invent tags. |
| Cached candidates to Replanner | Cache reuse is allowed only through `candidate_matches_constraint`. |
| Stable preferences to turn constraints | Stable preferences provide defaults; explicit turn constraints override them for the current turn only. |

## Design Decisions

### Parser Strategy

Regex will not be expanded into an exhaustive natural-language parser. It remains useful for:

- explicit ordinals: `第 2 站`, `第二站`, `stop 2`
- simple operations: replace/insert/remove
- obvious primary types: `公園`, `日式餐廳`

All other wording is handled by the LLM structured extractor. The extractor output is accepted only if validation succeeds.

### Vibe Tags

`vibe_tags` belong to the Data Service vocabulary. Chat_Agent must not maintain a complete hardcoded list. The LLM receives a bounded list of known tags and chooses a subset.

Fallback behavior:

- Tag catalog available and match found: strict `vibe_tag` filter may be used.
- Tag catalog available but no match: broader search with social sort, trace warning.
- Tag catalog unavailable: broader search, no invented tag, trace warning.

### Preference Hygiene

`Preferences` remain long-lived session memory. `TurnIntentFrame` is the executable representation of the current turn.

Stable fields:

- origin
- district
- time_window
- transport_mode
- language
- budget_level
- companions

Turn-specific fields:

- replacement category/type
- search place type
- category_mix
- vibe_tags for this request
- target stop reference

Explicit user corrections can update stable fields. Omitted or null extractor fields do not clear stable fields.

### Mixed Itinerary

When `category_mix` has multiple categories, AgentLoop should retrieve candidates per category and annotate each candidate with its source category. ItineraryBuilder must select from the resulting grouped candidates with a category pattern.

Initial patterns:

| Request | Category mix |
|---|---|
| `有玩有吃`, `景點加餐廳` | `["attraction", "food"]` |
| `逛街吃飯` | `["shopping", "food"]` |
| `咖啡廳和景點` | `["food", "attraction"]` with `primary_type`/keyword cafe bias |

## Implementation Phases

### Phase 1 - Data and Contract Foundation

- Add TurnIntentFrame and PlaceConstraint models in Chat_Agent.
- Add Data Service vibe-tag catalog contract and adapter method.
- Add tests for known-tag selection validation.

### Phase 2 - Replan Safety

- Extend replan parsing to produce target references and replacement constraints.
- Filter cached candidates against constraints.
- Refetch when cache does not match.
- Add regression tests for "second one", "park", "attraction", and cached-food failure cases.

### Phase 3 - Preference Hygiene

- Split stable preference updates from current-turn constraints.
- Prevent null/omitted fields from clearing existing session values.
- Add tests for old park request not polluting later restaurant request.

### Phase 4 - Vibe-Aware Retrieval

- Query known tags based on district/category context.
- Let LLM choose only known tags.
- Pass selected tags to `place_search`.
- Add recommend support or route vibe searches through search fallback.

### Phase 5 - Mixed Itinerary

- Detect category mixes in TurnIntentFrame.
- Execute per-category retrieval.
- Select itinerary stops with diversity constraints.
- Add tests for "有玩有吃" and "逛街吃飯".

### Phase 6 - Trace and Hardening

- Add trace details for frame validation, known tags, rejected tags, cache decisions, and relaxations.
- Add no-results behavior for overly strict tag/category mixes.
- Run full Chat_Agent test suite.

## Risk Analysis

| Risk | Mitigation |
|---|---|
| LLM chooses unsupported tags/types | Validate against known tags and allowed type/category maps; reject unknowns. |
| Tag catalog is too large | Limit by category/district and return top tags by count. |
| Repeated `vibe_tag` filters are too strict | Use relaxation: drop secondary tags, then use social sort. |
| Mixed itinerary has unbalanced data | Return explicit relaxation message and avoid pretending all constraints were satisfied. |
| Preference merge changes old behavior | Keep stable fields backward-compatible and add regression tests around null/omitted fields. |

## Success Gate

This spec is complete when the tasks in [tasks.md](./tasks.md) are implemented and the regression suite proves:

- replan target references and replacement constraints are validated;
- vibe tags are selected only from the Data Service catalog;
- cached candidates cannot violate replacement constraints;
- mixed itineraries include the requested categories when data exists;
- stable preferences survive LLM omissions/nulls.
