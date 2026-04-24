# Data Service Contract — Known Vibe Tags and Vibe-Aware Retrieval

**Owner**: `backend/Chitogo_DataBase`  
**Consumer**: `backend/Chat_Agent/app/tools/place_adapter.py`

This contract captures Data Service changes required by the Chat_Agent behavior in this spec.

## `GET /api/v1/places/vibe-tags`

Return the known normalized `vibe_tags` currently available in the database.

### Query Parameters

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `district` | string | no | Restrict tags to places in one Taipei district. |
| `internal_category` | enum | no | Restrict tags to one internal category. |
| `primary_type` | string | no | Restrict tags to a Google/Data Service primary type. |
| `limit` | int | no | Default 50, max 200. |

### Response

```json
{
  "items": [
    {
      "tag": "romantic",
      "place_count": 12,
      "mention_count": 38
    },
    {
      "tag": "scenic",
      "place_count": 31,
      "mention_count": 70
    }
  ],
  "limit": 50,
  "scope": {
    "district": "信義區",
    "internal_category": "food",
    "primary_type": null
  }
}
```

### Semantics

- `tag` must use the same normalization as social ingestion, e.g. `hidden gem` becomes `hidden_gem`.
- `place_count` counts distinct places whose aggregated `places.vibe_tags` contains the tag.
- `mention_count` may sum place-level `mention_count` for tagged places; if too expensive, it may be omitted or set to null.
- Results should be sorted by `place_count DESC`, then `mention_count DESC`, then tag ascending.
- Empty result is valid: `{"items": [], "limit": 50, "scope": {...}}`.

## `GET /api/v1/places/search`

Existing endpoint already supports repeatable `vibe_tag` query parameters.

### Required Behavior

```text
GET /api/v1/places/search?internal_category=food&primary_type=japanese_restaurant&vibe_tag=romantic
```

must return places matching all specified repeated tags using intersection semantics.

Supported social sorts:

- `mention_count_desc`
- `trend_score_desc`
- `sentiment_desc`

## `POST /api/v1/places/recommend` Extension

Vibe-aware recommend is preferred but may be implemented after search fallback.

### Request Extension

```json
{
  "districts": ["信義區"],
  "internal_category": "food",
  "vibe_tags": ["romantic"],
  "scenario": "date",
  "sort": "sentiment_desc",
  "limit": 10
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `vibe_tags` | `list[str]` | no | Known normalized tags. AND semantics when used as filters. |
| `scenario` | string | no | Optional ranking scenario such as `date`, `family`, `rainy_day`. |
| `sort` | enum | no | May use social sort values. |

### Ranking Guidance

For `scenario=date` or `vibe_tags` containing `romantic`, ranking should bias toward:

- `PlaceFeatures.couple_score`
- `Place.sentiment_score`
- `Place.rating`
- `Place.mention_count`

If recommend extension is not implemented initially, Chat_Agent must route vibe-aware requests through `/places/search`.
