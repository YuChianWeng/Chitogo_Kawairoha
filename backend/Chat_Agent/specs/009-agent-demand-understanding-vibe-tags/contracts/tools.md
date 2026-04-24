# Internal Tool Contract — Chat_Agent

This feature extends the existing Chat_Agent tool layer with a tag catalog lookup and stricter retrieval constraints.

## Tool: `place_vibe_tags`

Fetch known normalized Data Service vibe tags.

### Input

```json
{
  "district": "信義區",
  "internal_category": "food",
  "primary_type": "japanese_restaurant",
  "limit": 50
}
```

### Output

```json
{
  "status": "ok",
  "items": [
    {"tag": "romantic", "place_count": 12, "mention_count": 38}
  ],
  "error": null
}
```

### Error Semantics

- Timeout or malformed payload returns `status="error"` with `error`.
- Empty tag set returns `status="empty"` and `items=[]`.
- The caller must not fail the full chat turn solely because this tool errors.

## Tool: `place_search`

Existing tool, with required support for:

```json
{
  "district": "信義區",
  "internal_category": "food",
  "primary_type": "japanese_restaurant",
  "vibe_tags": ["romantic"],
  "min_mentions": 1,
  "sort": "sentiment_desc",
  "limit": 5
}
```

## Tool: `place_recommend`

May be extended with `vibe_tags`, `scenario`, and social sort. If not available, AgentLoop must choose `place_search` for vibe-aware requests.

## Candidate Matching Contract

Before reusing a cached candidate for replan replacement:

```python
candidate_matches_constraint(candidate, constraint) -> CandidateMatchDecision
```

must enforce all hard filters from `PlaceConstraint`.

Hard filters:

- internal category
- primary type
- district when specified
- all selected vibe tags
- indoor preference when specified
- max budget level when specified

If no cached candidate matches, AgentLoop must perform a fresh retrieval with the replacement constraint.
