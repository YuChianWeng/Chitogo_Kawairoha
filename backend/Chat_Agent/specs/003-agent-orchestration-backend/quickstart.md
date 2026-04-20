# Quickstart — Agent Orchestration Backend

How to run, exercise, and debug the Chat_Agent service locally.

---

## Prerequisites

- Python 3.11+
- The Place Data Service (`backend/Chitogo_DataBase`) running locally on `http://localhost:8000` with seeded venues.
- Environment variables:
  - `DATA_SERVICE_URL` — e.g., `http://localhost:8000`
  - `GOOGLE_MAPS_API_KEY` — Google Maps Directions API key (transit mode enabled)
  - `ANTHROPIC_API_KEY` — Claude API key
  - `SESSION_TTL_MIN` — optional, defaults to `30`

---

## Install and run

```bash
cd backend/Chat_Agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

Service comes up on `http://localhost:8100`.

---

## Sanity check

```bash
curl http://localhost:8100/api/v1/health
# {"status":"ok","data_service":"reachable"}
```

If `data_service` reports `degraded`, ensure `DATA_SERVICE_URL` is correct and the Data Service is running.

---

## Exercise the chat API

### 1. Itinerary generation

```bash
SID=$(uuidgen)
curl -sX POST http://localhost:8100/api/v1/chat/message \
  -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"Plan me a half-day in Ximending, vegetarian please.\"}" \
  | jq
```

Expect: `intent_classified="GENERATE_ITINERARY"`, populated `itinerary` with 3+ stops, `routing_status` in `["full","partial_fallback","failed"]`.

### 2. Replanning

```bash
curl -sX POST http://localhost:8100/api/v1/chat/message \
  -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"Replace stop 1 with a temple instead.\"}" \
  | jq
```

Expect: `intent_classified="REPLAN"`, only stop 1 changed, all other stops byte-for-byte identical to the previous response.

### 3. Explanation

```bash
curl -sX POST http://localhost:8100/api/v1/chat/message \
  -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"Why did you pick Longshan Temple?\"}" \
  | jq
```

Expect: `intent_classified="EXPLAIN"`, `itinerary=null`, `reply_text` cites at least one extracted preference.

### 4. Inspect the trace (demo "show your work")

```bash
curl -s http://localhost:8100/api/v1/chat/session/$SID/trace | jq
```

Expect: one `TraceEntry` per turn with the full `tool_calls` chain, latencies, and `composer_output`.

### 5. Inspect session state

```bash
curl -s "http://localhost:8100/api/v1/chat/session/$SID?include=traces" | jq
```

---

## Run tests

```bash
cd backend/Chat_Agent
pytest                                  # full suite
pytest tests/unit/                      # unit only (no network)
pytest tests/integration/               # spins up FastAPI TestClient with mocks
pytest tests/contract/                  # checks Data Service schema (requires Data Service running)
pytest -k "fallback"                    # all route-fallback paths
pytest --cov=app --cov-report=term-missing
```

---

## Useful demo scenarios

| Scenario | Trigger |
|---|---|
| Cold start, no preferences | Send a fresh `session_id` and a vague request to see the clarifying-question path. |
| Preference accumulation | Turn 1: "I'm vegetarian." Turn 2: "I don't like crowds." Turn 3: "Plan me a day." → should respect both. |
| Route fallback | Set `GOOGLE_MAPS_API_KEY=invalid` and replay scenario 1. Expect `routing_status="failed"` and all legs `estimated=true`. |
| Session expiry | Send a turn, wait `SESSION_TTL_MIN+1` minutes, send another. Response should include `session_recreated: true`. |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 data_service_unreachable` on every request | `DATA_SERVICE_URL` wrong or Data Service not running | Check `curl $DATA_SERVICE_URL/api/v1/places/stats`. |
| All itineraries have `routing_status="failed"` | Google API key invalid or transit mode not enabled | Test directly: `curl "https://maps.googleapis.com/maps/api/directions/json?origin=25.04,121.50&destination=25.05,121.51&mode=transit&key=$GOOGLE_MAPS_API_KEY"`. |
| `intent_classified="CHAT_GENERAL"` for clear itinerary requests | Classifier rules too narrow | Inspect `app/orchestration/classifier.py`; LLM fallback should be hitting — check `tests/unit/test_classifier.py` fixtures. |
| Per-turn latency > 10 s | Anthropic model too large or tool fan-out too wide | Lower `agent_loop.max_iterations` or switch to Haiku for the classifier. |
