# Data Model — Constraint-Aware Demand Understanding and Vibe Tags

**Date**: 2026-04-24  
**Storage**: New Chat_Agent models are in-memory/request-scoped unless explicitly merged into `Session.preferences`.  
**Validation**: Pydantic v2 models with deterministic validation after LLM extraction.

## Entity Overview

```text
Session
├── Preferences                     # long-lived stable memory
├── latest_itinerary
├── cached_candidates
└── current turn
     └── TurnIntentFrame
          ├── stable_preference_delta
          ├── search_constraint
          ├── replacement_constraint
          ├── target_reference
          ├── category_mix
          └── vibe_tag_selection
```

## TurnIntentFrame

Per-turn executable request frame. This is the contract between NLU and orchestration.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `intent` | `Intent` | required | `GENERATE_ITINERARY`, `REPLAN`, `EXPLAIN`, `CHAT_GENERAL`. |
| `source` | `Literal["regex", "llm", "hybrid"]` | required | Explains how the frame was created. |
| `confidence` | `float` | 0..1 | Low confidence frames require clarification. |
| `needs_clarification` | `bool` | required | Set after validation, not trusted from LLM alone. |
| `missing_fields` | `list[str]` | default `[]` | E.g. `["target_reference"]`, `["replacement_constraint"]`. |
| `stable_preference_delta` | `Preferences \| None` | optional | Safe fields to merge into session. |
| `search_constraint` | `PlaceConstraint \| None` | optional | Discovery/generation search request. |
| `replacement_constraint` | `PlaceConstraint \| None` | required for replace/insert with specified replacement | Replan-specific constraint. |
| `target_reference` | `TargetReference \| None` | required for replan operations except global replan | Validated against current itinerary. |
| `operation` | `Literal["replace", "insert", "remove"] \| None` | required for `REPLAN` | |
| `category_mix` | `list[CategoryMixItem]` | default `[]` | Used for mixed itinerary generation. |
| `vibe_tag_selection` | `VibeTagSelection \| None` | optional | Records known selected/rejected tags. |
| `raw_user_message` | `str` | required | Stored in trace, may be truncated. |

### Validation Rules

- If `intent == REPLAN`, `operation` must be present.
- If `operation in {"replace", "remove"}`, `target_reference.resolved_index` must be valid unless clarification is required.
- If `operation in {"replace", "insert"}` and the user specified a replacement type/vibe, `replacement_constraint` must be present.
- `vibe_tags` in constraints must be a subset of known Data Service tags when a tag catalog was available.

## PlaceConstraint

Retrieval and candidate-matching constraints for a current turn.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `district` | `str \| None` | valid Taipei district | Defaults from stable preferences if omitted. |
| `internal_category` | `str \| None` | Data Service internal category | `food`, `attraction`, `shopping`, `lodging`, `transport`, `nightlife`, `other`. |
| `primary_type` | `str \| None` | len <= 128 | Google/Data Service type, e.g. `park`, `japanese_restaurant`. |
| `keyword` | `str \| None` | len <= 80 | Used only when type/category vocabulary is insufficient. |
| `vibe_tags` | `list[str]` | known tags only | Repeatable `vibe_tag` filters. |
| `min_mentions` | `int \| None` | >= 0 | Optional social proof filter. |
| `sort` | `PlaceSort \| None` | supported Data Service sort | e.g. `rating_desc`, `trend_score_desc`, `sentiment_desc`. |
| `max_budget_level` | `int \| None` | 0..4 | Derived from stable budget preference. |
| `indoor` | `bool \| None` | optional | Derived from stable or turn-specific preference. |
| `open_now` | `bool \| None` | optional | |

### Constraint Matching

A cached candidate matches a constraint only if all specified hard filters match:

- `internal_category` equals candidate category.
- `primary_type` equals candidate primary type or is present in raw type payload if available.
- every requested `vibe_tag` exists in candidate `vibe_tags`.
- `district` equals candidate district when district is specified as hard.
- budget/indoor filters match when specified.

## TargetReference

Validated reference to a stop in an existing itinerary.

| Field | Type | Notes |
|---|---|---|
| `kind` | `Literal["index", "ordinal", "relative", "name", "unknown"]` | How the user referred to the stop. |
| `raw_text` | `str \| None` | Original phrase, e.g. `第二個`. |
| `resolved_index` | `int \| None` | Zero-based stop index after validation. |
| `confidence` | `float` | Low confidence requires clarification. |

### Supported Fast-Path References

- `第N站`, `第 N 站`
- `第N個`, `第N間`, `第N家`
- Chinese ordinals: `第一`, `第二`, `第三`, `最後一站`
- English ordinals: `first stop`, `second stop`, `last stop`

Non-fast-path references may be resolved by the LLM if validation succeeds.

## VibeTagCatalog

Data Service-provided list of known tags.

| Field | Type | Notes |
|---|---|---|
| `items` | `list[VibeTagItem]` | Sorted by place count, mention count, or relevance. |
| `scope` | `dict` | The district/category/type filters used to build the catalog. |

### VibeTagItem

| Field | Type | Notes |
|---|---|---|
| `tag` | `str` | Normalized tag from Data Service. |
| `place_count` | `int` | Number of places currently carrying this tag. |
| `mention_count` | `int \| None` | Optional total social mentions. |

## VibeTagSelection

LLM-selected tag subset and validation outcome.

| Field | Type | Notes |
|---|---|---|
| `selected_tags` | `list[str]` | Must be subset of catalog tags. |
| `rejected_tags` | `list[str]` | Tags proposed by LLM but rejected. |
| `confidence` | `float` | LLM confidence after prompt; backend may downgrade. |
| `fallback_strategy` | `Literal["none", "broaden_search", "social_sort_only"]` | Used when no strict known tag match exists. |

## CategoryMixItem

| Field | Type | Notes |
|---|---|---|
| `internal_category` | `str` | Desired category. |
| `primary_type` | `str \| None` | Optional type bias within category. |
| `min_count` | `int` | Minimum desired stops from this category. |
| `weight` | `float` | Relative preference when total stop count is limited. |

## CandidateMatchDecision

Trace-only model for cache filtering.

| Field | Type | Notes |
|---|---|---|
| `candidate_id` | `int \| str` | Candidate being considered. |
| `candidate_name` | `str` | |
| `matched` | `bool` | |
| `failed_fields` | `list[str]` | e.g. `["internal_category", "vibe_tags"]`. |
| `constraint_summary` | `dict` | Sanitized summary of the active constraint. |

## Preference Merge Semantics

### Stable Session Preferences

Stable preferences are merged into session only when explicitly provided with a meaningful value:

- `origin`
- `district`
- `time_window`
- `companions`
- `budget_level`
- `transport_mode`
- `indoor_preference`
- `language`

Omitted keys and explicit `null` values from the LLM do not clear existing values by default.

### Turn-Specific Constraints

These should usually remain inside `TurnIntentFrame` and not be merged globally:

- `search_constraint.primary_type`
- `replacement_constraint`
- `category_mix`
- `vibe_tags`
- one-off keywords such as `park`, `japanese_restaurant`, `romantic`

The only exception is when the user clearly states a durable preference, such as "之後都幫我找安靜一點的地方".
