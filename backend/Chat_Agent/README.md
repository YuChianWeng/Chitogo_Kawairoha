# Chat_Agent

## Startup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

The service exposes `GET /api/v1/health` and probes the external Data Service over HTTP. It does not access the place database directly.
Environment values are loaded from `.env`, including `CORS_ALLOW_ORIGINS` as a comma-separated list such as `http://localhost:3000,http://localhost:5173`.
Gemini is the default LLM provider for the orchestration backend:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-pro
```

Anthropic remains available as optional compatibility for later phases by setting `LLM_PROVIDER=anthropic` and providing `ANTHROPIC_API_KEY`.

Phase 4 adds typed external tool adapters:
- `PlaceToolAdapter` wraps the retrieval service at `DATA_SERVICE_BASE_URL`
- `RouteToolAdapter` uses Google Maps when available and falls back to haversine estimates

Optional adapter settings:

```env
PLACE_SERVICE_TIMEOUT_SEC=3
ROUTE_PROVIDER=google_maps
ROUTE_SERVICE_TIMEOUT_SEC=3
```

## Tests

```bash
pytest tests/test_config.py tests/test_health.py tests/test_llm_client.py
```
