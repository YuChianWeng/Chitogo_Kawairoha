# Internal Tool Contracts — Chat_Agent

These are the internal tool interfaces consumed by the LLM Agent Loop. Each tool has:

1. A **Python adapter signature** (consumed in code).
2. An **LLM-facing tool schema** (the JSON schema registered with Anthropic for tool-use).
3. A **failure contract** (how errors propagate back into the agent loop).

The `ToolRegistry` (`app/tools/registry.py`) owns the list of registered tools and filters them per intent (see `research.md` R-011).

---

## Tool index

| Name | Adapter | Backed by | Exposed to intents |
|---|---|---|---|
| `place_search` | `PlaceToolAdapter.search` | Data Service `GET /api/v1/places/search` | All except `EXPLAIN` |
| `place_recommend` | `PlaceToolAdapter.recommend` | Data Service `POST /api/v1/places/recommend` | `GENERATE_ITINERARY` |
| `place_nearby` | `PlaceToolAdapter.nearby` | Data Service `GET /api/v1/places/nearby` | `GENERATE_ITINERARY`, `REPLAN` |
| `place_batch` | `PlaceToolAdapter.batch` | Data Service `POST /api/v1/places/batch` | `GENERATE_ITINERARY`, `REPLAN` |
| `place_categories` | `PlaceToolAdapter.categories` | Data Service `GET /api/v1/places/categories` | `GENERATE_ITINERARY` |
| `place_stats` | `PlaceToolAdapter.stats` | Data Service `GET /api/v1/places/stats` | `GENERATE_ITINERARY` |
| `route_estimate` | `RouteToolAdapter.estimate_leg` | Google Maps Directions API (transit mode) + haversine fallback | `GENERATE_ITINERARY`, `REPLAN` |

---

## `place_search`

Search Taipei places with structured filters.

### Adapter

```python
async def search(self, params: PlaceSearchParams) -> PlaceListResult: ...

class PlaceSearchParams(BaseModel):
    district: str | None = None
    internal_category: Literal["attraction","food","shopping","lodging","transport","nightlife","other"] | None = None
    primary_type: str | None = None
    keyword: str | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_budget_level: int | None = Field(default=None, ge=0, le=4)
    indoor: bool | None = None
    open_now: bool | None = None
    sort: Literal["rating_desc","user_rating_count_desc"] = "rating_desc"
    limit: int = Field(default=20, ge=1, le=100)

class PlaceListResult(BaseModel):
    items: list[Place]
    total: int
```

### LLM-facing schema

```json
{
  "name": "place_search",
  "description": "Search Taipei venues by district, category, rating, budget, indoor/outdoor. Returns up to 'limit' places sorted by rating or user rating count.",
  "input_schema": {
    "type": "object",
    "properties": {
      "district": {"type": "string", "description": "Taipei district name (e.g., 'Wanhua')"},
      "internal_category": {"type": "string", "enum": ["attraction","food","shopping","lodging","transport","nightlife","other"]},
      "keyword": {"type": "string"},
      "min_rating": {"type": "number", "minimum": 0, "maximum": 5},
      "max_budget_level": {"type": "integer", "minimum": 0, "maximum": 4},
      "indoor": {"type": "boolean"},
      "open_now": {"type": "boolean"},
      "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}
    }
  }
}
```

### Failure contract

Adapter raises `PlaceToolError` on transport / 5xx / timeout. The agent loop catches it and surfaces a tool result of the form `{"error": "place_tool_error", "detail": "..."}` to the LLM, which decides whether to retry, broaden filters, or give up.

---

## `place_recommend`

Get scored recommendations across one or more districts.

### Adapter

```python
async def recommend(self, params: RecommendParams) -> PlaceListResult: ...

class RecommendParams(BaseModel):
    districts: list[str] | None = None
    internal_category: Literal[...] | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_budget_level: int | None = Field(default=None, ge=0, le=4)
    indoor: bool | None = None
    open_now: bool | None = None
    limit: int = Field(default=10, ge=1, le=50)
```

Each returned `Place` carries an extra `recommendation_score: float` for the LLM to consider.

### LLM-facing schema

```json
{
  "name": "place_recommend",
  "description": "Get scored Taipei venue recommendations. Use when you want top-k picks for an itinerary slot rather than a raw search.",
  "input_schema": {
    "type": "object",
    "properties": {
      "districts": {"type": "array", "items": {"type": "string"}},
      "internal_category": {"type": "string", "enum": ["attraction","food","shopping","lodging","transport","nightlife","other"]},
      "min_rating": {"type": "number", "minimum": 0, "maximum": 5},
      "max_budget_level": {"type": "integer", "minimum": 0, "maximum": 4},
      "indoor": {"type": "boolean"},
      "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}
    }
  }
}
```

### Failure contract

Same as `place_search`.

---

## `place_nearby`

Find venues within a radius of a coordinate. Used heavily during replanning to find substitutes near an existing stop.

### Adapter

```python
async def nearby(self, params: NearbyParams) -> NearbyListResult: ...

class NearbyParams(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: int = Field(gt=0, le=5000)   # MAX_NEARBY_RADIUS_M from Data Service
    internal_category: Literal[...] | None = None
    primary_type: str | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_budget_level: int | None = Field(default=None, ge=0, le=4)
    limit: int = Field(default=20, ge=1, le=100)
    sort: Literal["distance_asc","rating_desc","user_rating_count_desc"] = "distance_asc"
```

Returns `NearbyPlace = Place + {distance_m: float}`.

### LLM-facing schema

```json
{
  "name": "place_nearby",
  "description": "Find venues within radius_m meters of a lat/lng. Use for 'something near stop X' or 'replace this stop with something close by' queries.",
  "input_schema": {
    "type": "object",
    "required": ["lat", "lng", "radius_m"],
    "properties": {
      "lat": {"type": "number"},
      "lng": {"type": "number"},
      "radius_m": {"type": "integer", "minimum": 100, "maximum": 5000},
      "internal_category": {"type": "string", "enum": ["attraction","food","shopping","lodging","transport","nightlife","other"]},
      "min_rating": {"type": "number", "minimum": 0, "maximum": 5},
      "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10}
    }
  }
}
```

### Failure contract

Same as `place_search`.

---

## `place_batch`

Fetch full details for a list of place IDs. Used after the LLM has chosen its candidate set, to confirm and enrich before composing the itinerary.

### Adapter

```python
async def batch(self, place_ids: list[int]) -> list[PlaceDetail]: ...
```

Constraint: `1 <= len(place_ids) <= 100`.

### LLM-facing schema

```json
{
  "name": "place_batch",
  "description": "Fetch full details for a list of venue IDs. Use after you've chosen which venues to include, to get accurate addresses, hours, and coordinates.",
  "input_schema": {
    "type": "object",
    "required": ["place_ids"],
    "properties": {
      "place_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 1,
        "maxItems": 50
      }
    }
  }
}
```

### Failure contract

Same as `place_search`.

---

## `place_categories`

Return the list of internal categories with their representative Google place types.

### Adapter

```python
async def categories(self) -> list[Category]: ...

class Category(BaseModel):
    value: str
    label: str
    representative_types: list[str]
```

### LLM-facing schema

```json
{
  "name": "place_categories",
  "description": "List the available venue categories and what each one covers. Use when you're unsure which 'internal_category' value to pass to other tools.",
  "input_schema": {"type": "object", "properties": {}}
}
```

### Failure contract

Same as `place_search`. Result is small; safe to call once per session and cache.

---

## `place_stats`

Aggregate counts per district/category. Useful for the LLM when deciding district mix.

### Adapter

```python
async def stats(self) -> PlaceStats: ...

class PlaceStats(BaseModel):
    total_places: int
    by_district: dict[str, int]
    by_internal_category: dict[str, int]
    by_primary_type: dict[str, int]
```

### LLM-facing schema

```json
{
  "name": "place_stats",
  "description": "Get aggregate counts of venues by district and category, useful for sanity-checking what data is available before suggesting a district.",
  "input_schema": {"type": "object", "properties": {}}
}
```

### Failure contract

Same as `place_search`.

---

## `route_estimate`

Estimate transit time between two coordinates. **Never raises on routing failure** — returns `estimated=True` with a haversine fallback.

### Adapter

```python
async def estimate_leg(
    self,
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    depart_at: datetime | None = None,
) -> RouteResult: ...

class RouteResult(BaseModel):
    transit_method: Literal["transit", "walking", "estimated"]
    duration_min: int
    estimated: bool
```

### LLM-facing schema

```json
{
  "name": "route_estimate",
  "description": "Estimate public transit travel time in minutes between two coordinates in Taipei. Returns the duration and the transit method used. If live routing is unavailable the result will fall back to a distance-based estimate (estimated=true).",
  "input_schema": {
    "type": "object",
    "required": ["from_lat", "from_lng", "to_lat", "to_lng"],
    "properties": {
      "from_lat": {"type": "number"},
      "from_lng": {"type": "number"},
      "to_lat": {"type": "number"},
      "to_lng": {"type": "number"},
      "depart_at": {"type": "string", "format": "date-time", "description": "ISO 8601 departure time; defaults to now if omitted"}
    }
  }
}
```

### Failure contract

The adapter never raises. On any HTTP error, parse failure, or no-route response: returns `RouteResult(transit_method="estimated", duration_min=<haversine/12kmh>, estimated=True)`.

The Composer is responsible for aggregating `estimated` flags into `routing_status`:

| Condition | `routing_status` |
|---|---|
| All legs `estimated == False` | `"full"` |
| Some legs `estimated == True`, some `False` | `"partial_fallback"` |
| All legs `estimated == True` | `"failed"` |

---

## Tool-call recording

Every tool invocation is timed and appended to the in-progress `TraceEntry.tool_calls` list before the next tool is invoked. Output recording is truncated to the first 50 items for list-shaped responses to bound memory.
