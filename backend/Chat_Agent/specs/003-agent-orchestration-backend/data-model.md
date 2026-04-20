# Data Model — Agent Orchestration Backend

**Date**: 2026-04-20
**Storage**: All entities live in-memory inside the `Session` object, owned by `SessionStore`. No database for v1.
**Validation**: Pydantic v2 models. All field-level constraints below are enforced at construction time.

---

## Entity Overview

```
Session ───┬── Turn[]
           ├── Preferences
           ├── Itinerary?
           │      ├── Stop[]
           │      └── Leg[]
           ├── Place[]              (cached candidate set)
           └── TraceEntry[]
                    └── ToolCallRecord[]
```

---

## Session

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `session_id` | `UUID` | required, well-formed | Client-generated. Validated at API boundary. |
| `created_at` | `datetime` | required, UTC | Set on first observation of `session_id`. |
| `last_active_at` | `datetime` | required, UTC | Updated on every read or write (`SessionManager.touch`). Drives 30-min TTL. |
| `preferences` | `Preferences` | required | Defaults to empty `Preferences()`. |
| `turns` | `list[Turn]` | required, default `[]` | Append-only across the session. |
| `current_itinerary` | `Itinerary \| None` | optional | Set after a `GENERATE_ITINERARY` or `REPLAN` turn succeeds. |
| `candidate_places` | `list[Place]` | required, default `[]` | Last batch of place results returned by a tool call; used by `Replanner` to avoid re-fetching. |
| `traces` | `list[TraceEntry]` | required, default `[]`, max 50 entries (FIFO eviction) | Per-turn observability records. |

### State Transitions

- **Create** → first request with a previously unseen `session_id`.
- **Touch** → on every API request.
- **Expire** → background sweeper deletes the session when `now - last_active_at > 30 min`.
- **Recreate** → if a request arrives with a UUID whose session was just expired, a fresh `Session` is created and `session_recreated=true` is included in the response.

---

## Turn

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `turn_id` | `UUID` | required | Server-generated. |
| `role` | `Literal["user", "assistant"]` | required | |
| `content` | `str` | required, len 1..4000 | Raw message text. |
| `created_at` | `datetime` | required, UTC | |

---

## Preferences

All fields optional. Merge semantics: each call to `PreferenceExtractor` returns a delta; missing keys leave existing values untouched, explicit `None` clears a value, lists overwrite (corrections supersede earlier statements).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `activity_types` | `list[str]` | optional, default `[]` | Free-form tags chosen by the LLM (`"temple"`, `"night_market"`, `"cafe"`). |
| `dietary` | `list[str]` | optional, default `[]` | E.g., `["vegetarian"]`, `["halal"]`. |
| `budget_level` | `int \| None` | 0..4 | Maps to Data Service `max_budget_level`. |
| `mobility` | `Literal["walking", "transit", "any"] \| None` | optional | Influences `route_estimate` mode preference. |
| `time_window` | `TimeWindow \| None` | optional | See below. |
| `districts` | `list[str]` | optional, default `[]` | Taipei district names matching Data Service `district` field. |
| `language` | `Literal["en", "zh-TW"]` | required, default `"en"` | Detected at first turn; can change per turn if the user switches. |
| `crowd_tolerance` | `Literal["low", "moderate", "high"] \| None` | optional | |

### TimeWindow

| Field | Type | Notes |
|---|---|---|
| `start` | `str` | `"HH:MM"` 24-hour, Taipei local. |
| `end` | `str` | `"HH:MM"` 24-hour, Taipei local. |

---

## Itinerary

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `itinerary_id` | `UUID` | required | Server-generated. New ID on each full regeneration; preserved on partial replan. |
| `summary` | `str` | required, len 1..200 | Short headline for the chat bubble. |
| `total_duration_min` | `int` | ≥ 0 | Sum of `visit_duration_min` + leg `duration_min`. |
| `stops` | `list[Stop]` | min length 1 | Ordered by `stop_index` (0-based, dense). |
| `legs` | `list[Leg]` | length == `len(stops) - 1` | One leg between each consecutive pair. |
| `created_at` | `datetime` | required, UTC | |

### Validation Rules

- `stops` must have dense `stop_index` values starting at 0.
- For every `Leg`, `from_stop` and `to_stop` must be valid indices in `stops`, and `to_stop == from_stop + 1`.
- `total_duration_min == sum(s.visit_duration_min for s in stops) + sum(l.duration_min for l in legs)`.

---

## Stop

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `stop_index` | `int` | ≥ 0 | Stable for the lifetime of the itinerary; addressable target for `REPLAN`. |
| `venue_id` | `int` | required | Data Service `Place.id`. |
| `venue_name` | `str` | required, len 1..200 | From Data Service `display_name`. |
| `category` | `str` | required | One of the Data Service `internal_category` values (`attraction`, `food`, `shopping`, `lodging`, `transport`, `nightlife`, `other`). |
| `arrival_time` | `str` | matches `^\d{2}:\d{2}$` | Taipei local time. |
| `visit_duration_min` | `int` | 1..480 | Default per category (R-007). |
| `lat` | `float` | -90..90 | |
| `lng` | `float` | -180..180 | |

---

## Leg

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `from_stop` | `int` | ≥ 0 | Index into `Itinerary.stops`. |
| `to_stop` | `int` | == `from_stop + 1` | |
| `transit_method` | `Literal["transit", "walking", "estimated"]` | required | `"estimated"` only when `estimated=True`. |
| `duration_min` | `int` | ≥ 0 | |
| `estimated` | `bool` | required | `True` when `RouteToolAdapter` used the haversine fallback. |

---

## Place (cached candidate)

Mirrors Data Service `PlaceCandidateOut` 1:1. Stored to allow `Replanner` to operate without re-fetching.

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | Data Service primary key. |
| `google_place_id` | `str` | |
| `display_name` | `str` | |
| `primary_type` | `str \| None` | Google primary_type. |
| `district` | `str \| None` | Taipei district. |
| `formatted_address` | `str \| None` | |
| `rating` | `float \| None` | 0..5 |
| `user_rating_count` | `int \| None` | |
| `price_level` | `str \| None` | |
| `budget_level` | `str \| None` | Data Service convention (`"0"`..`"4"` or null). |
| `internal_category` | `str` | One of the 7 internal categories. |
| `latitude` | `float \| None` | |
| `longitude` | `float \| None` | |
| `indoor` | `bool \| None` | |
| `outdoor` | `bool \| None` | |
| `business_status` | `str \| None` | |
| `google_maps_uri` | `str \| None` | |

---

## TraceEntry

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `turn_id` | `UUID` | required | Matches the `Turn.turn_id` it describes. |
| `intent_classified` | `Literal["GENERATE_ITINERARY", "REPLAN", "EXPLAIN", "CHAT_GENERAL"]` | required | |
| `tool_calls` | `list[ToolCallRecord]` | default `[]` | In-order log of every tool invocation. |
| `composer_output` | `dict` | required | Snapshot of the API response payload. |
| `total_latency_ms` | `int` | ≥ 0 | Wall-clock per-turn latency. |
| `fallback_used` | `bool` | required | True if any leg in this turn used the haversine fallback. |
| `final_status` | `Literal["ok", "partial_fallback", "error"]` | required | Mirrors `routing_status` for itinerary turns; otherwise `"ok"` or `"error"`. |

### ToolCallRecord

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | One of: `place_search`, `place_recommend`, `place_nearby`, `place_batch`, `place_categories`, `place_stats`, `route_estimate`. |
| `input` | `dict` | The arguments passed to the tool. |
| `output` | `dict` | The result returned (may be truncated to first 50 items for list-shaped results to keep memory bounded). |
| `latency_ms` | `int` | Per-call wall-clock. |

---

## Intent Slot Schemas (per intent)

Output of `IntentClassifier`. Used by `AgentLoop` and `Composer` for deterministic gating.

### `GENERATE_ITINERARY`
| Slot | Type | Required | Notes |
|---|---|---|---|
| `districts` | `list[str]` | optional | |
| `duration_hint` | `str` | optional | `"half-day"`, `"1-day"`, `"3-hours"`, etc. |
| `start_time` | `str` | optional | `"HH:MM"` |
| `categories` | `list[str]` | optional | |
| `needs_clarification` | `bool` | required | True when no actionable info was extracted. |

### `REPLAN`
| Slot | Type | Required | Notes |
|---|---|---|---|
| `operation` | `Literal["replace", "insert", "remove"]` | required | MVP: only `replace` is implemented. |
| `stop_index` | `int` | required for `replace`/`remove` | |
| `replacement_hint` | `str` | optional | Free-form description of what to replace with. |

### `EXPLAIN`
| Slot | Type | Required | Notes |
|---|---|---|---|
| `subject` | `Literal["whole_itinerary", "stop", "leg"]` | required | |
| `target_index` | `int \| None` | optional | Stop or leg index when `subject != "whole_itinerary"`. |

### `CHAT_GENERAL`
| Slot | Type | Required | Notes |
|---|---|---|---|
| `topic_hint` | `str` | optional | Free-form summary of what the user asked, used by the LLM. |
