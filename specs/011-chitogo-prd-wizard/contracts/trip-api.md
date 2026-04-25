# Trip API Contract

**Service**: Chat Agent (`backend/Chat_Agent/`) on port 8100  
**Router prefix**: `/api/v1/trip`  
**Auth**: None (session_id in request body / query param)  
**Error format**: `{"detail": "code:message"}` with HTTP 4xx/5xx

All state-violation errors return HTTP 400 with detail `"state_error:expected_{STATE}"`.

---

## POST /api/v1/trip/quiz

Submit quiz answers and receive travel gene classification.

**Allowed state**: `QUIZ`  
**Transitions to**: `TRANSPORT`

### Request
```json
{
  "session_id": "string (required — create via existing /api/v1/chat/sessions if needed)",
  "answers": {
    "Q1": "A | B | C",
    "Q2": "A | B",
    "Q3": "A | B",
    "Q4": "A | B",
    "Q5": "A | B",
    "Q6": "A | B",
    "Q7": "A | B",
    "Q8": "A | B",
    "Q9": "A | B"
  }
}
```

**Validation**: Q1 accepts A/B/C; Q2–Q9 accept A/B only. All 9 keys required.

### Response 200
```json
{
  "session_id": "string",
  "travel_gene": "文清 | 親子 | 不常來 | 夜貓子 | 一日 | 野外",
  "mascot": "string (mascot identifier)",
  "gene_description": "string (short description of the travel gene)"
}
```

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:expected_QUIZ` | Session not in QUIZ state |
| 400 `quiz_error:missing_answers` | Fewer than 9 answers provided |
| 400 `quiz_error:invalid_answer:{Qn}` | Answer not A/B/C for Q1 or A/B for Q2–Q9 |
| 404 `session_not_found` | Unknown session_id |

---

## POST /api/v1/trip/setup

Configure accommodation, return time, and transport mode.

**Allowed state**: `TRANSPORT`  
**Transitions to**: `RECOMMENDING`

### Request
```json
{
  "session_id": "string",
  "accommodation": {
    "booked": true,
    "hotel_name": "string (required if booked=true)",
    "district": "string (required if booked=false)",
    "budget_tier": "budget | mid | luxury (optional if booked=false)"
  },
  "return_time": "HH:MM (optional)",
  "return_destination": "hotel | string (station name, optional)",
  "transport": {
    "modes": ["walk", "transit", "drive"],
    "max_minutes_per_leg": 30
  }
}
```

### Response 200
```json
{
  "session_id": "string",
  "accommodation_status": "validated | fuzzy_match | not_found | not_required",
  "hotel_validation": {
    "valid": true,
    "matched_name": "string",
    "match_type": "exact | fuzzy",
    "confidence": 0.95,
    "district": "string",
    "address": "string",
    "alternatives": [
      {"name": "string", "district": "string", "address": "string", "confidence": 0.82}
    ],
    "last_updated": "2026-04-25"
  },
  "setup_complete": true
}
```

`hotel_validation` is `null` when `accommodation.booked = false`.  
`alternatives` is an empty list when `match_type = "exact"`.

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:expected_TRANSPORT` | Not in TRANSPORT state |
| 400 `setup_error:hotel_name_required` | booked=true but hotel_name missing |
| 400 `setup_error:invalid_return_time` | return_time not HH:MM |
| 400 `setup_error:empty_transport_modes` | modes list is empty |
| 400 `setup_error:invalid_transport_mode:{mode}` | Unknown mode value |

---

## GET /api/v1/trip/candidates

Retrieve 6 venue candidates for current location.

**Allowed state**: `RECOMMENDING`  
**State unchanged after call**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | yes | |
| `lat` | float | yes | Current location latitude |
| `lng` | float | yes | Current location longitude |

### Response 200
```json
{
  "session_id": "string",
  "candidates": [
    {
      "venue_id": "string | int",
      "name": "string",
      "category": "restaurant | attraction",
      "primary_type": "string | null",
      "address": "string | null",
      "lat": 25.0478,
      "lng": 121.5170,
      "rating": 4.2,
      "distance_min": 12,
      "why_recommended": "string (one sentence)"
    }
  ],
  "partial": false,
  "fallback_reason": "null | string",
  "restaurant_count": 3,
  "attraction_count": 3
}
```

`partial: true` when 3+3 split was not achievable.  
`fallback_reason` explains any time-limit extension applied.

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:expected_RECOMMENDING` | Not in RECOMMENDING state |
| 400 `candidates_error:invalid_coordinates` | lat/lng out of range |
| 503 `candidates_error:data_service_unavailable` | Cannot reach Place Data Service |

---

## POST /api/v1/trip/select

User selects a venue from the candidate set.

**Allowed state**: `RECOMMENDING`  
**Transitions to**: `RATING`

### Request
```json
{
  "session_id": "string",
  "venue_id": "string | int",
  "current_lat": 25.0478,
  "current_lng": 121.5170
}
```

### Response 200
```json
{
  "session_id": "string",
  "venue": {
    "venue_id": "string | int",
    "name": "string",
    "category": "restaurant | attraction",
    "address": "string",
    "lat": 25.0478,
    "lng": 121.5170
  },
  "navigation": {
    "google_maps_url": "https://maps.google.com/?daddr=25.0478,121.5170&travelmode=transit",
    "apple_maps_url": "maps://maps.apple.com/?daddr=25.0478,121.5170",
    "estimated_travel_min": 12
  },
  "encouragement_message": "string (LLM-generated, 1–2 sentences)"
}
```

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:expected_RECOMMENDING` | Not in RECOMMENDING state |
| 400 `select_error:venue_not_in_candidates` | venue_id not in last candidate set |

---

## POST /api/v1/trip/rate

Submit star rating after a visit. Call after user confirms "我到了！".

**Allowed state**: `RATING`  
**Transitions to**: `RECOMMENDING`

### Request
```json
{
  "session_id": "string",
  "stars": 4,
  "tags": ["食物很好吃", "值得再來"]
}
```

`stars` must be 1–5. `tags` is optional (empty list if omitted).

### Response 200
```json
{
  "session_id": "string",
  "visit_recorded": true,
  "stop_number": 3,
  "affinity_update": {
    "category": "cafe",
    "adjustment": 0.2
  }
}
```

`affinity_update.adjustment` is +0.2 for 5★, −0.3 for 1–2★, 0 for 3–4★.

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:expected_RATING` | Not in RATING state |
| 400 `rate_error:invalid_stars` | stars not 1–5 |

---

## POST /api/v1/trip/demand

User taps "None of these" — submit free-text demand for 3 alternative venues.

**Allowed state**: `RECOMMENDING`  
**State unchanged after call**

### Request
```json
{
  "session_id": "string",
  "demand_text": "我想找有點文藝的地方",
  "lat": 25.0478,
  "lng": 121.5170
}
```

### Response 200
```json
{
  "session_id": "string",
  "alternatives": [
    {
      "venue_id": "string | int",
      "name": "string",
      "category": "restaurant | attraction",
      "primary_type": "string | null",
      "address": "string | null",
      "lat": 25.0478,
      "lng": 121.5170,
      "rating": 4.2,
      "distance_min": 8,
      "why_recommended": "string"
    }
  ],
  "fallback_reason": "null | string"
}
```

Always returns 1–3 items. `fallback_reason` explains if fewer than 3 available.

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:expected_RECOMMENDING` | Not in RECOMMENDING state |
| 400 `demand_error:empty_text` | demand_text is blank |

---

## GET /api/v1/trip/should_go_home

Polled by frontend every 60 seconds to check if "該回家了" reminder should fire.

**Allowed states**: `RECOMMENDING`, `RATING`  
**State unchanged after call**

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | yes | |
| `lat` | float | yes | Current latitude |
| `lng` | float | yes | Current longitude |

### Response 200
```json
{
  "session_id": "string",
  "remind": false,
  "message": "null | string",
  "time_remaining_min": "null | int"
}
```

`remind: true` fires when `now >= return_time − transit_to_dest − 30 min`.  
Once `remind: true` is returned, the session sets `go_home_reminded_at = now`; subsequent calls within 10 minutes return `remind: false`.

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:not_in_trip` | Session not in RECOMMENDING or RATING |

---

## GET /api/v1/trip/summary

Retrieve full journey summary. Calling this endpoint when state is RECOMMENDING or RATING transitions the session to ENDED.

**Allowed states**: `RECOMMENDING`, `RATING`, `ENDED`  
**Transitions to**: `ENDED` (if not already)

### Query Parameters
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | yes | |

### Response 200
```json
{
  "session_id": "string",
  "travel_gene": "string",
  "mascot": "string",
  "stops": [
    {
      "stop_number": 1,
      "venue_id": "string | int",
      "venue_name": "string",
      "category": "restaurant | attraction",
      "address": "string | null",
      "arrived_at": "2026-04-25T10:30:00Z",
      "star_rating": 4,
      "tags": ["食物很好吃"]
    }
  ],
  "total_stops": 3,
  "total_elapsed_min": 240,
  "total_distance_m": 5200,
  "mascot_farewell": "string (LLM-generated farewell message)"
}
```

### Errors
| Code | Meaning |
|------|---------|
| 400 `state_error:trip_not_started` | Session still in QUIZ or TRANSPORT |
| 404 `session_not_found` | Unknown session_id |
