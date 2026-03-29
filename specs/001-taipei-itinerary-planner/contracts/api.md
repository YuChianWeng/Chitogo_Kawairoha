# API Contract: Taipei AI Itinerary Planner

**Base URL**: `http://localhost:8000` (dev) | `https://<deploy-host>` (prod)
**Version**: v1
**Format**: JSON request/response, UTF-8
**Auth**: None (MVP)
**CORS**: All origins allowed in dev; restrict to frontend origin in prod

---

## POST /api/v1/itinerary

Generate a personalized same-day Taipei itinerary based on user preferences and current weather.

### Request

```
POST /api/v1/itinerary
Content-Type: application/json
```

**Body** (`UserPreferencesRequest`):

```json
{
  "district":    "daan",
  "start_time":  "10:00",
  "end_time":    "14:00",
  "interests":   ["food", "cafes"],
  "budget":      "mid",
  "companion":   "solo",
  "indoor_pref": "no_preference"
}
```

| Field | Type | Required | Default | Allowed Values |
|-------|------|----------|---------|---------------|
| `district` | string | No | `"daan"` | `daan`, `zhongzheng`, `wanhua`, `zhongshan`, `xinyi`, `shilin`, `beitou`, `songshan` |
| `start_time` | string | No | `"10:00"` | `"HH:MM"` 24-hour format |
| `end_time` | string | No | `"14:00"` | `"HH:MM"` 24-hour, must be ≥ 60 min after `start_time` |
| `interests` | string[] | No | `["food","cafes"]` | 1–5 items from tag vocabulary |
| `budget` | string | No | `"mid"` | `budget`, `mid`, `splurge` |
| `companion` | string | No | `"solo"` | `solo`, `couple`, `family`, `friends` |
| `indoor_pref` | string | No | `"no_preference"` | `indoor`, `outdoor`, `no_preference` |

**Interest tag vocabulary**: `food`, `cafes`, `art`, `history`, `shopping`, `nature`, `nightlife`, `family`, `instagrammable`, `local`, `trendy`, `quiet`, `budget-friendly`, `upscale`

---

### Response — 200 OK

```json
{
  "itinerary_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "generated_at": "2026-03-29T10:00:00Z",
  "weather": {
    "condition":         "rain",
    "temperature_c":     18.5,
    "precipitation_pct": 80,
    "icon":              "rain"
  },
  "stops": [
    {
      "order":                    1,
      "venue_id":                 "venue_042",
      "name":                     "Fushan Café",
      "category":                 "cafe",
      "address":                  "No. 12, Fuxing S. Rd, Da'an District",
      "lat":                      25.0330,
      "lon":                      121.5432,
      "indoor":                   true,
      "cost_level":               2,
      "tags":                     ["cafes", "food", "instagrammable"],
      "arrival_time":             "10:00",
      "dwell_minutes":            60,
      "travel_to_next_minutes":   10,
      "reason": "Fushan Café is a cozy indoor spot in Da'an that's been trending among solo visitors this week — a perfect warm shelter for a rainy morning with great coffee and brunch."
    },
    {
      "order":                    2,
      "venue_id":                 "venue_018",
      "name":                     "Taiwan Folk Arts Museum",
      "category":                 "museum",
      "address":                  "32 Zhongqing St, Datong District",
      "lat":                      25.0560,
      "lon":                      121.5100,
      "indoor":                   true,
      "cost_level":               1,
      "tags":                     ["history", "art", "local"],
      "arrival_time":             "11:10",
      "dwell_minutes":            75,
      "travel_to_next_minutes":   8,
      "reason": "A budget-friendly indoor museum showcasing traditional Taiwanese crafts — ideal for a rainy late morning when you want shelter and cultural depth."
    }
  ],
  "total_stops":            4,
  "total_duration_minutes": 240,
  "metadata": {
    "weather_fallback": false,
    "filter_relaxed":   false
  }
}
```

**Response fields**:

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `itinerary_id` | string (UUID) | No | Client-facing ID for the generated itinerary |
| `generated_at` | string (ISO-8601) | No | UTC generation timestamp |
| `weather` | object | Yes | Null when weather API was unavailable |
| `weather.condition` | string | No | `clear`, `cloudy`, `rain`, `drizzle`, `thunderstorm`, `snow`, `unknown` |
| `weather.temperature_c` | float | Yes | Celsius |
| `weather.precipitation_pct` | integer | Yes | 0–100 |
| `weather.icon` | string | Yes | Icon key for UI rendering |
| `stops` | array | No | Ordered list of 3–5 stops |
| `stops[].order` | integer | No | 1-based position |
| `stops[].venue_id` | string | No | Stable venue identifier |
| `stops[].name` | string | No | Venue name |
| `stops[].category` | string | No | Venue category |
| `stops[].address` | string | Yes | Street address |
| `stops[].lat` | float | No | Latitude |
| `stops[].lon` | float | No | Longitude |
| `stops[].indoor` | boolean | No | True = predominantly indoor |
| `stops[].cost_level` | integer | No | 1=cheap, 2=mid, 3=upscale |
| `stops[].tags` | string[] | No | Interest tags |
| `stops[].arrival_time` | string | No | `"HH:MM"` suggested arrival |
| `stops[].dwell_minutes` | integer | No | Expected time at this stop |
| `stops[].travel_to_next_minutes` | integer | No | Travel time to next stop; 0 for last stop |
| `stops[].reason` | string | No | 1–2 sentence personalized explanation |
| `total_stops` | integer | No | Number of stops (3–5) |
| `total_duration_minutes` | integer | No | Time from first arrival to last departure |
| `metadata` | object | Yes | Debug/fallback flags |
| `metadata.weather_fallback` | boolean | No | True if weather API was unavailable |
| `metadata.filter_relaxed` | boolean | No | True if district/indoor filters were relaxed |

---

### Response — 400 Bad Request

Returned when validation fails (e.g., time range too short, invalid field value).

```json
{
  "error_code": "time_range_too_short",
  "message":    "Your selected time range is less than 60 minutes. Please allow at least 1 hour for a meaningful itinerary.",
  "details": {
    "start_time": "13:30",
    "end_time":   "14:00",
    "duration_minutes": 30
  }
}
```

**Error codes**:

| `error_code` | Condition |
|-------------|-----------|
| `time_range_too_short` | `end_time - start_time < 60 minutes` |
| `invalid_district` | `district` not in allowed enum |
| `invalid_budget` | `budget` not in `[budget, mid, splurge]` |
| `invalid_indoor_pref` | `indoor_pref` not in allowed enum |
| `too_many_interests` | `interests` array has more than 5 items |

---

### Response — 500 Internal Server Error

```json
{
  "error_code": "itinerary_generation_failed",
  "message":    "We encountered an unexpected problem generating your itinerary. Please try again.",
  "request_id": "f47ac10b-58cc"
}
```

---

## GET /api/v1/health

Liveness check. Returns immediately without hitting any external services.

### Response — 200 OK

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

## GET /api/v1/venues

Returns the full list of venues from the seed dataset. Intended for debug and admin use during hackathon development; not exposed in the production UI.

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `district` | string | — | Filter by district |
| `category` | string | — | Filter by category |
| `indoor` | boolean | — | Filter by indoor flag |
| `limit` | integer | 100 | Max results |

### Response — 200 OK

```json
{
  "total": 80,
  "venues": [
    {
      "id":                 "venue_001",
      "name":               "Yongkang Street Café District",
      "district":           "daan",
      "category":           "cafe",
      "tags":               ["cafes", "food", "local"],
      "lat":                25.0330,
      "lon":                121.5322,
      "indoor":             true,
      "cost_level":         2,
      "avg_dwell_minutes":  60,
      "trend_score":        0.75
    }
  ]
}
```

---

## Client-Side Notes (Frontend)

- All requests originate from `frontend/src/services/api.ts` via Axios
- The frontend should display a loading skeleton while the request is in-flight (target ≤ 10 s)
- If `weather` is `null` in the response, the `WeatherBadge` component is hidden
- If `metadata.weather_fallback` is `true`, show a subtle "Weather data unavailable" footnote
- If `metadata.filter_relaxed` is `true`, show a subtle "Nearby districts included" footnote
- Stop cards are rendered in `stops[].order` ascending order
- `travel_to_next_minutes` for the last stop will always be `0` — do not render a travel indicator for it
