# Chat API Contract — Frontend ↔ Chat_Agent

**Base path**: `/api/v1/chat/`
**Authentication**: None (v1 hackathon).
**Content type**: `application/json` for all requests and responses.

All endpoints are owned by `app/api/v1/chat.py`.

---

## `POST /api/v1/chat/message`

Submit a user message. Server runs the full per-turn pipeline (classify → extract preferences → agent loop → compose) and returns the assistant reply.

### Request

```json
{
  "session_id": "8f3c1d2a-4b5e-6789-abcd-ef0123456789",
  "message": "Plan me a half-day in Ximending, vegetarian please."
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `session_id` | string (UUID) | yes | Must be a well-formed UUID. Server creates the session implicitly if unseen or expired. |
| `message` | string | yes | 1..4000 chars. |

### Response — `200 OK`

```json
{
  "session_id": "8f3c1d2a-4b5e-6789-abcd-ef0123456789",
  "turn_id": "1a2b3c4d-…",
  "session_recreated": false,
  "intent_classified": "GENERATE_ITINERARY",
  "reply_text": "Here's a 4-stop afternoon plan around Ximending — all spots are vegetarian-friendly. We start at Longshan Temple at 13:00…",
  "routing_status": "full",
  "itinerary": {
    "itinerary_id": "9d4e7f1a-…",
    "summary": "Afternoon in Ximending — vegetarian-friendly",
    "total_duration_min": 240,
    "stops": [
      {
        "stop_index": 0,
        "venue_id": 1042,
        "venue_name": "Longshan Temple",
        "category": "attraction",
        "arrival_time": "13:00",
        "visit_duration_min": 60,
        "lat": 25.0372,
        "lng": 121.4999
      }
    ],
    "legs": [
      {
        "from_stop": 0,
        "to_stop": 1,
        "transit_method": "transit",
        "duration_min": 12,
        "estimated": false
      }
    ]
  }
}
```

| Field | Type | Always Present | Notes |
|---|---|---|---|
| `session_id` | string | yes | Echoes the request. |
| `turn_id` | string (UUID) | yes | Server-generated. |
| `session_recreated` | bool | yes | `true` only when the prior session for this UUID had expired. |
| `intent_classified` | enum | yes | One of `GENERATE_ITINERARY`, `REPLAN`, `EXPLAIN`, `CHAT_GENERAL`. |
| `reply_text` | string | yes | Always non-empty; the chat-bubble narrative. |
| `routing_status` | enum | yes for itinerary turns, `"full"` otherwise | One of `full`, `partial_fallback`, `failed`. |
| `itinerary` | object \| null | always present, may be `null` | `null` for `EXPLAIN` and `CHAT_GENERAL` turns; populated for `GENERATE_ITINERARY` and `REPLAN`. |

### Error responses

| Status | Body | Trigger |
|---|---|---|
| `400 invalid_session_id` | `{"error": "invalid_session_id", "detail": "session_id must be a valid UUID"}` | Malformed UUID. |
| `400 message_too_long` | `{"error": "message_too_long", "detail": "message exceeds 4000 chars"}` | |
| `502 data_service_unreachable` | `{"error": "data_service_unreachable", "detail": "…"}` | Place adapter raised `PlaceToolError` AND no useful response could be composed. |
| `500 internal_error` | `{"error": "internal_error"}` | Unhandled exception in the pipeline. |

---

## `GET /api/v1/chat/session/{session_id}`

Fetch the current state of a session.

### Path params
- `session_id`: UUID.

### Query params
- `include` (optional): comma-separated. Supported values: `traces`. Default omits traces to keep payloads small.

### Response — `200 OK`

```json
{
  "session_id": "…",
  "created_at": "2026-04-20T05:01:00Z",
  "last_active_at": "2026-04-20T05:14:22Z",
  "preferences": { /* Preferences */ },
  "turns": [ /* Turn[] */ ],
  "current_itinerary": { /* Itinerary or null */ },
  "traces": [ /* TraceEntry[] — only if ?include=traces */ ]
}
```

### Error responses

| Status | Body | Trigger |
|---|---|---|
| `404 session_not_found` | `{"error": "session_not_found"}` | UUID is well-formed but unknown to the store. |

---

## `GET /api/v1/chat/session/{session_id}/trace`

Fetch the per-turn observability trace for the demo "show your work" panel.

### Response — `200 OK`

```json
{
  "session_id": "…",
  "count": 3,
  "traces": [
    {
      "turn_id": "…",
      "intent_classified": "GENERATE_ITINERARY",
      "tool_calls": [
        {
          "name": "place_recommend",
          "input": {"districts": ["Ximending"], "internal_category": "attraction", "limit": 5},
          "output": { /* truncated to first 50 items */ },
          "latency_ms": 142
        },
        {
          "name": "route_estimate",
          "input": {"from_lat": 25.04, "from_lng": 121.50, "to_lat": 25.05, "to_lng": 121.51},
          "output": {"transit_method": "transit", "duration_min": 12, "estimated": false},
          "latency_ms": 387
        }
      ],
      "composer_output": { /* the response payload as returned to the user */ },
      "total_latency_ms": 4821,
      "fallback_used": false,
      "final_status": "ok"
    }
  ]
}
```

### Error responses

| Status | Body | Trigger |
|---|---|---|
| `404 session_not_found` | `{"error": "session_not_found"}` | |

---

## `DELETE /api/v1/chat/session/{session_id}`

Explicit teardown. Idempotent.

### Response — `204 No Content`

No body. Returns `204` even if the session was already absent.

---

## `GET /api/v1/health`

Liveness probe. Performs a 1-second timeout `GET` to the Data Service `/api/v1/health` (or `/api/v1/places/stats` if no health endpoint exists in the Data Service).

### Response — `200 OK`

```json
{
  "status": "ok",
  "data_service": "reachable"
}
```

`data_service` is `"reachable"` or `"degraded"`. Never blocks startup.

---

## Conventions

- All UUIDs are RFC-4122 v4 strings, lowercase.
- All timestamps are ISO 8601 in UTC (`Z` suffix). `arrival_time` strings inside itinerary stops are local Taipei `HH:MM` (no date).
- Errors use the envelope `{"error": "<code>", "detail": "<optional human-readable>"}`.
- The agent backend logs every request with `session_id` and `turn_id` for cross-referencing with the trace endpoint.
