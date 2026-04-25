# Quickstart — Validation Scenarios

This quickstart describes the manual flows that should pass after implementation. It assumes:

- Data Service is running on port `8000`.
- Chat_Agent is running on port `8100`.
- Chat_Agent has a valid LLM provider configuration.
- Data Service contains social `vibe_tags` such as `romantic`, `scenic`, or `hidden_gem`.

## 1. Start Services

```bash
cd backend/Chitogo_DataBase
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
cd backend/Chat_Agent
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8100
```

## 2. Verify Known Vibe Tags

```bash
curl 'http://127.0.0.1:8000/api/v1/places/vibe-tags?internal_category=food&limit=20'
```

Expected:

```json
{
  "items": [
    {"tag": "romantic", "place_count": 1, "mention_count": 1}
  ]
}
```

The exact tags depend on local data, but the endpoint must return normalized tag strings.

## 3. Generate a Food-Heavy Itinerary

```bash
curl -X POST 'http://127.0.0.1:8100/api/v1/chat/message' \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "從信義區出發下午開始然後找浪漫的餐廳"
  }'
```

Save the returned `session_id`.

Expected:

- itinerary starts in the afternoon;
- selected places are food venues;
- if `romantic` exists in known tags, retrieval uses it or records why it was not used.

## 4. Replace "Second One" With Attraction

```bash
curl -X POST 'http://127.0.0.1:8100/api/v1/chat/message' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "<SESSION_ID>",
    "message": "可以把第二個換成景點嗎"
  }'
```

Expected:

- response intent is `REPLAN`;
- stop index 1 is changed;
- replacement category is not `food`;
- unchanged stops are preserved where possible.

## 5. Replace Third Stop With Park

```bash
curl -X POST 'http://127.0.0.1:8100/api/v1/chat/message' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "<SESSION_ID>",
    "message": "第三站換成公園"
  }'
```

Expected:

- stop index 2 becomes park-like or attraction-like;
- cached restaurant candidates are not reused unless they satisfy the park constraint, which they should not.

## 6. Romantic Japanese Restaurant

```bash
curl -X POST 'http://127.0.0.1:8100/api/v1/chat/message' \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "<SESSION_ID>",
    "message": "幫我找一間日式餐廳浪漫一點的"
  }'
```

Expected:

- search constraint includes Japanese restaurant type;
- if known tags include `romantic`, query includes `vibe_tag=romantic`;
- old park constraints from prior replan do not pollute this request.

## 7. Mixed "Play and Eat" Itinerary

```bash
curl -X POST 'http://127.0.0.1:8100/api/v1/chat/message' \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "幫我排一個有玩有吃的行程下午從大安區出發"
  }'
```

Expected:

- itinerary contains at least one `attraction` stop and one `food` stop when data exists;
- first arrival time is at or after `13:00`;
- response does not claim a mixed itinerary if only one category was available after relaxation.

## 8. Inspect Trace

```bash
curl 'http://127.0.0.1:8100/api/v1/chat/traces?session_id=<SESSION_ID>&limit=5'
```

Then fetch a trace detail:

```bash
curl 'http://127.0.0.1:8100/api/v1/chat/traces/<TRACE_ID>'
```

Expected trace details include:

- turn frame validation;
- known vibe tag count and selected tags;
- cache candidate matching/refetch decision;
- category mix retrieval steps.
