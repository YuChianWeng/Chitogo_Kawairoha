# Chat API Contract — Constraint-Aware Behavior

**Base path**: `/api/v1/chat/`  
**Owner**: `backend/Chat_Agent/app/api/v1/chat.py`  
**Compatibility**: This feature should not require a breaking public response schema change.

## `POST /api/v1/chat/message`

The request body remains:

```json
{
  "session_id": "8f3c1d2a-4b5e-6789-abcd-ef0123456789",
  "message": "第三站換成公園",
  "user_context": {
    "lat": 25.033,
    "lng": 121.565
  }
}
```

## Behavioral Contract

### Replan With Replacement Type

**Given** an existing itinerary, **when** the user says:

```text
可以把第二個換成景點嗎
```

The response must either:

- return `intent=REPLAN`, `needs_clarification=false`, and an itinerary whose stop index 1 satisfies `internal_category=attraction`; or
- return `needs_clarification=true` with a targeted question if the target cannot be validated.

It must not replace the stop with a food venue.

### Replan With Park Type

**Given** an existing itinerary, **when** the user says:

```text
第三站換成公園
```

The response must use a replacement that satisfies either:

- `primary_type=park`, `city_park`, or another validated park-like type; or
- `internal_category=attraction` with a park keyword/type fallback.

### Vibe-Aware Discovery

**When** the user says:

```text
幫我找一間日式餐廳浪漫一點的
```

and the current or following turn supplies required stable context such as origin/time, the final retrieval path must include:

- `internal_category=food`
- `primary_type=japanese_restaurant` or equivalent validated type
- `vibe_tag=romantic` if the Data Service known tag catalog includes `romantic`

### Mixed Itinerary

**When** the user says:

```text
幫我排一個有玩有吃的行程下午從大安區出發
```

the itinerary response must include:

- at least one `food` stop when food candidates exist;
- at least one `attraction` stop when attraction candidates exist;
- first stop arrival time at or after `13:00` unless user gave a different explicit time.

## Trace Contract

The existing trace endpoints may be extended with step details. A trace for affected turns should include steps similar to:

```json
{
  "name": "turn_frame.validate",
  "status": "success",
  "detail": {
    "intent": "REPLAN",
    "operation": "replace",
    "target_index": 1,
    "replacement_internal_category": "attraction",
    "replacement_primary_type": null,
    "selected_vibe_tags": []
  }
}
```

For vibe selection:

```json
{
  "name": "vibe_tags.select",
  "status": "success",
  "detail": {
    "known_tag_count": 25,
    "selected_tags": ["romantic"],
    "rejected_tags": []
  }
}
```

For cache matching:

```json
{
  "name": "replan.cache_candidate_filter",
  "status": "fallback",
  "detail": {
    "candidate_count": 5,
    "matched_count": 0,
    "refetch_required": true
  }
}
```

## Error and Clarification Behavior

If the frame cannot be validated, return the normal chat response envelope with:

```json
{
  "intent": "REPLAN",
  "needs_clarification": true,
  "message": "你想調整哪一站？可以說第一站、第二站或最後一站。"
}
```

If known tags are unavailable, the assistant should not return a 500 solely because tag selection failed. It should use broader search and record a trace warning.
