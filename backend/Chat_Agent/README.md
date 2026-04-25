# Chitogo Chat Agent Backend

## Overview

Chitogo Chat Agent Backend is a FastAPI-based orchestration backend for a Taipei travel chat assistant. It accepts natural-language user messages, identifies intent, extracts preferences, maintains session state, and calls external place-data and routing tools when needed to return either place candidates or a structured short itinerary.

This repository does not solve place-data storage itself. Its job is to make the chat workflow concrete: intent classification, preference understanding, turn-level constraint validation, tool orchestration, itinerary generation, partial replanning, and request trace/debug capture. Place data currently comes from an external Data Service. Travel-time estimation uses Google Maps Directions first and falls back to distance-based estimates when needed.

At the moment, this project is a runnable, test-covered backend prototype. The main APIs and core flow are in place, but session state and traces are still stored in memory, so the service is not yet production-grade in areas such as persistence, authentication, rate limiting, or multi-instance state sharing.

## Current Features

### Chat Entry Point and Session State

- A single chat entry point is exposed at `POST /api/v1/chat/message`.
- If a request does not include `session_id`, the backend creates a new UUID. If `session_id` is provided, it must be a valid UUID or the API returns `400 invalid_session_id`.
- Session state stores chat turns, merged preferences, the latest itinerary, and cached place candidates.
- Requests for the same session are processed under a per-session lock to avoid concurrent state corruption.
- A background TTL sweeper periodically removes stale sessions.

### Intent Detection and Preference Understanding

- `IntentClassifier` is now LLM-first and returns structured JSON slots for `GENERATE_ITINERARY`, `REPLAN`, `EXPLAIN`, or `CHAT_GENERAL`, with a safe fallback to `CHAT_GENERAL` if parsing fails.
- The currently supported high-level intents are `GENERATE_ITINERARY`, `REPLAN`, `EXPLAIN`, and `CHAT_GENERAL`.
- `PreferenceExtractor` is LLM-driven and normalizes provider output into canonical session preferences, including district, origin, companions, budget, transport, time window, and interest tags.
- District validation remains deterministic, and explicit phrases such as `從大安區出發` are normalized into usable `district` / `origin` session data.
- The backend currently understands origin, district, time window, companions, budget, transport mode, indoor/outdoor preference, interest tags, avoid tags, and language hint.
- Language handling is currently centered on `zh-TW` and `en`, and responses adapt accordingly.

### Recommendations and Place Lookup

- The backend queries an external Data Service for `search`, `recommend`, and `nearby` place results and normalizes them into `ToolPlace`.
- Direct place-finding messages such as “幫我找一個好玩的公園” or “找一間浪漫的日式餐廳” enter discovery/search instead of falling back to generic chat or itinerary-only clarification.
- `AgentLoop` now uses an LLM planning step for `place_recommend`, `place_search`, and `place_nearby`, with deterministic validation and fallback when the plan is invalid or the LLM call fails.
- For known interest tags such as `cafes`, deterministic query mapping still wins over free-text tool params so the final query stays aligned with Data Service vocabulary like `food` + `cafe`.
- When vibe language is present, Chat_Agent first requests the known Data Service `vibe_tags`, records the selection decision in trace, and only sends validated tags downstream.
- Planned `place_search` requests automatically fall back to `place_recommend` when the search returns no matches.
- The place adapter retries once on 5xx responses, and returns structured error results for timeouts or malformed payloads instead of crashing the request.

### Itinerary Generation

- The backend can build a structured `Itinerary` with `stops`, `legs`, `arrival_time`, and `total_duration_min`.
- It currently uses simple heuristics to choose between 2 and 4 stops based on the requested time window. If no time window is available, it defaults to 3 stops.
- Relative time hints such as `下午` / `afternoon` are normalized into an afternoon window, so itinerary arrival times do not silently fall back to the morning default.
- Mixed requests such as `有玩有吃` or `逛街吃飯` trigger one retrieval per requested category and the itinerary builder now tries to preserve category diversity before falling back to generic ranking.
- Travel time between stops is estimated through Google Maps Directions when available.
- If Google Maps is unavailable, or `ROUTE_PROVIDER=fallback` is configured, the backend falls back to Haversine-distance estimates.
- The response includes `routing_status`, which can be `full`, `partial_fallback`, or `failed`.

### Replanning and Explanation

- The backend supports replacing, inserting, or removing a single stop from an existing itinerary.
- Replan parsing keeps a regex fast path for clear ordinal references, and falls back to the LLM when the operation or stop reference is ambiguous.
- Replanning tries to preserve unaffected stops and legs, and only rebuilds the parts that need to change.
- `EXPLAIN` responses are based on cached session candidates and current preferences; they do not trigger fresh external tool calls.

### Trace, Debug, and Logging

- Every chat request produces a trace with step names, status, duration, warnings, and error summary.
- Trace detail now includes validated turn-frame summaries, selected known vibe tags, cache candidate filtering for replans, and category-mix retrieval / relaxation decisions.
- The API exposes both recent-trace listing and single-trace detail endpoints, with optional `session_id` filtering.
- Trace storage is a bounded in-memory buffer that evicts older entries once the configured limit is exceeded.
- Application logs are emitted as structured JSON events.

## Architecture and Module Guide

- `app/main.py`
  FastAPI app factory and module-level `app` entry point. It wires CORS, lifespan handling, the TTL sweeper, and shared app state.
- `app/api/v1/chat.py`
  Public chat and trace endpoints, including error envelopes and app-state dependency resolution.
- `app/api/v1/health.py`
  Health endpoint. It currently probes the external Data Service at `/api/v1/places/stats`.
- `app/chat/message_handler.py`
  The main single-turn orchestration service. It ties together session access, classification, preference extraction, tool orchestration, itinerary building, replanning, response composition, and trace recording.
- `app/chat/loop.py`
  Hybrid tool planning for `place_search`, `place_recommend`, and `place_nearby`, with LLM planning plus deterministic validation and fallback.
- `app/chat/itinerary_builder.py`
  Builds itineraries, enriches legs with route estimates, assigns arrival times, and computes routing status.
- `app/chat/replanner.py`
  Parses replanning requests with regex fast paths plus LLM fallback, then applies replace / insert / remove operations.
- `app/orchestration/`
  LLM-backed intent classification, preference extraction, language hints, and slot parsing. This layer is intentionally decoupled from the tool layer.
- `app/session/`
  Session models, in-memory store, mutation API, and TTL sweeper.
- `app/tools/`
  Place Data Service adapter, Google Maps route adapter, and the `ToolRegistry`.
- `app/llm/client.py`
  Lazy Gemini / Anthropic / OpenRouter wrapper exposing `generate_text` and `generate_json`, with OpenRouter HTTP support and retry handling.
- `app/core/config.py`
  Environment-variable loading and validation. The app reads settings at startup/import time.
- `tests/`
  Test suite run through `pytest`, with most tests written in `unittest` / `IsolatedAsyncioTestCase` style.
- `specs/003-agent-orchestration-backend/`
  Historical spec and design documents. Treat the code under `app/` as the current source of truth.

Additional notes:

- `ToolRegistry` currently registers `place_batch`, `place_categories`, and `place_stats`, but the main chat flow primarily uses `place_search`, `place_recommend`, `place_nearby`, and `route_estimate`.
- Some repo-side helper documents still mention the older `src/` path layout. The actual implementation lives under `app/`.

## API Summary

### Product-Facing API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/chat/message` | Single-turn chat entry point. Main request fields are `session_id?`, `message`, and optional `user_context.lat/lng`. The response includes `intent`, `preferences`, and, when applicable, `candidates`, `itinerary`, `routing_status`, `tool_results_summary`, and `source`. |
| `GET` | `/api/v1/health` | Basic service health plus Data Service reachability. `status` can be `ok` or `degraded`. |

### Debug / Operational API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/chat/traces` | Returns recent traces. Supports `limit` (`1-200`) and optional `session_id` filtering. |
| `GET` | `/api/v1/chat/traces/{trace_id}` | Returns the full trace detail for a single request. Returns 404 if the trace is not found. |

### OpenAPI

- FastAPI docs are available at `/docs`.
- The OpenAPI schema is available at `/openapi.json`.

## Running the Service

### Prerequisites

- Python 3.11
- Access to the external Place Data Service
- A valid Google Maps Directions API key if using `ROUTE_PROVIDER=google_maps`
- A Gemini, Anthropic, or OpenRouter API key for the LLM-backed paths

### Local Development Setup

This repo uses `requirements.txt` and does not currently ship with a `pyproject.toml` or `Makefile`. The example below uses `python3`, which avoids issues on systems that do not expose a global `python` binary:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export PYTHONPATH=.
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

If you prefer not to activate the virtual environment, you can run:

```bash
PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

### Startup Path and Notes

- FastAPI entry point: `app.main:app`
- App factory: `app.main:create_app`
- Because `app = create_app()` runs at import time, environment variables must be available before startup/import.
- `HOST` and `PORT` are required settings, but the actual bind address still comes from the `uvicorn` command you run.

### Minimal `.env` Example

```env
APP_ENV=development
HOST=0.0.0.0
PORT=8100
DATA_SERVICE_BASE_URL=http://localhost:8000
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
CORS_ALLOW_ORIGINS=http://localhost:3000,http://localhost:5173
LOG_LEVEL=INFO
```

### OpenRouter `.env` Example

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=deepseek/deepseek-v3.2
OPENROUTER_FALLBACK_MODEL=deepseek/deepseek-v3.2
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

## Environment Variables

### Required

| Variable | Description |
| --- | --- |
| `APP_ENV` | Required by the settings model. Currently used mainly for startup validation and environment labeling. |
| `HOST` | Required by the settings model. It is not automatically passed into `uvicorn`. |
| `PORT` | Required by the settings model. It is not automatically passed into `uvicorn`. |
| `DATA_SERVICE_BASE_URL` | Base URL for the external Place Data Service. Used by both the health probe and `PlaceToolAdapter`. |
| `CORS_ALLOW_ORIGINS` | Comma-separated list of allowed origins for FastAPI CORS middleware. |
| `LOG_LEVEL` | Logging level consumed by `configure_logging()`. |
| `GOOGLE_MAPS_API_KEY` | Used by `RouteToolAdapter`. At the moment, the settings model still requires it even when `ROUTE_PROVIDER=fallback`. |
| `GEMINI_API_KEY` | Required when `LLM_PROVIDER=gemini`. |
| `ANTHROPIC_API_KEY` | Required when `LLM_PROVIDER=anthropic`. |
| `OPENROUTER_API_KEY` | Required when `LLM_PROVIDER=openrouter`. |

### Common Optional Variables

| Variable | Description |
| --- | --- |
| `LLM_PROVIDER` | `gemini`, `anthropic`, or `openrouter`. Defaults to `gemini`. |
| `GEMINI_MODEL` | Default Gemini model. Defaults to `gemini-2.5-flash`. |
| `GEMINI_FALLBACK_MODEL` | Fallback Gemini model. Defaults to `gemini-2.5-pro`. |
| `ANTHROPIC_MODEL` | Default Anthropic model. Defaults to `claude-sonnet-4-6`. |
| `ANTHROPIC_FALLBACK_MODEL` | Fallback Anthropic model. Defaults to `claude-haiku-4-5-20251001`. |
| `OPENROUTER_MODEL` | Default OpenRouter model. Defaults to `openai/gpt-4.1-mini`; the current demo setup commonly uses `deepseek/deepseek-v3.2`. |
| `OPENROUTER_FALLBACK_MODEL` | Fallback OpenRouter model. Defaults to `openai/gpt-4.1`; the current demo setup commonly uses `deepseek/deepseek-v3.2`. |
| `OPENROUTER_BASE_URL` | OpenRouter API base URL. Defaults to `https://openrouter.ai/api/v1`. |
| `PLACE_SERVICE_TIMEOUT_SEC` | Timeout for Place Data Service requests. Defaults to `3`. |
| `ROUTE_PROVIDER` | `google_maps` or `fallback`. Defaults to `google_maps`. |
| `ROUTE_SERVICE_TIMEOUT_SEC` | Timeout for Google Maps route requests. Defaults to `3`. |
| `SESSION_TTL_MINUTES` | Idle-session TTL. Defaults to `30` minutes. |
| `TRACE_STORE_MAX_ITEMS` | Max size of the in-memory trace buffer. Defaults to `200`. Supported by the code, but not listed in the current `.env.example`. |

### Defined but Not Fully Wired Yet

| Variable | Current Status |
| --- | --- |
| `AGENT_LOOP_MAX_ITERATIONS` | Defined and validated in `Settings`, but not currently used by `AgentLoop`. |
| `REQUEST_TIMEOUT_S` | Defined and validated in `Settings`, but not currently consumed by the main request flow. |
| `DEFAULT_START_TIME` | Default itinerary start time when the current turn and retained preferences do not provide a time window. Defaults to `10:00`. |

## Testing

The test suite runs through `pytest`, while most individual tests are written in `unittest` style. The current suite has 178 passing tests. Because the repo is not currently installed as a package, add the repo root to `PYTHONPATH` when running tests:

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

Useful targeted commands:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_chat_api.py tests/test_message_handler.py -q
PYTHONPATH=. .venv/bin/pytest tests/test_place_adapter.py tests/test_route_adapter.py -q
PYTHONPATH=. .venv/bin/pytest tests/test_trace_api.py tests/test_trace_store.py -q
```

## Current Limitations and Notes

- Session state, cached candidates, and recent traces are all stored in memory. Restarting the process loses them, and this is not suitable for shared multi-instance state.
- The project does not access a place database directly. All place retrieval depends on the external Data Service.
- `GET /api/v1/health` only checks Data Service reachability. It does not verify Google Maps or LLM-provider availability.
- Even with `ROUTE_PROVIDER=fallback`, the current settings validation still requires `GOOGLE_MAPS_API_KEY`.
- `HOST` and `PORT` are required settings, but they do not automatically control the actual `uvicorn` bind address.
- `EXPLAIN` depends on cached session candidates. If the cache is empty, the explanation degrades to a generic response.
- Discovery routing still relies on bounded heuristics plus validated LLM output. Unsupported phrasing should degrade into broader search or clarification, but the system is not a free-form semantic planner.
- Mixed-category itineraries still use bounded heuristics for stop selection and route ordering; they do not yet solve a global optimization problem.
- The current scope is Taipei recommendations and short itineraries, not a general-purpose trip planner.
- Some helper documents in the repo still contain early-phase path or structure references. Treat the implementation under `app/` and the tests as authoritative.

## Recommended Next Steps

- Move session and trace storage to a persistent backing store if the service needs longer-lived or multi-instance state.
- Clean up configuration wiring so `GOOGLE_MAPS_API_KEY`, `AGENT_LOOP_MAX_ITERATIONS`, and `REQUEST_TIMEOUT_S` either fully work or are removed.
- Add formal packaging or a task runner so tests do not require manual `PYTHONPATH=.` setup.
- If the external Data Service contract will evolve frequently, add contract tests or stub-server-backed integration tests.

## Project Layout

```text
app/
  main.py                    FastAPI app factory and module-level app
  api/v1/                    HTTP endpoints
  chat/                      Main orchestration flow, itinerary building, replanning, traces
  orchestration/             Intent, preference, language, and slot parsing
  session/                   In-memory session models, store, manager, TTL sweeper
  tools/                     Place Data Service and route adapters, tool registry
  llm/                       Gemini / Anthropic / OpenRouter wrapper
  core/                      Settings and logging
tests/                       Pytest test suite
specs/003-agent-orchestration-backend/
                             Historical spec and design docs
requirements.txt             Python dependencies
pytest.ini                   Pytest configuration
```
