# ChitoGo (Taipei Trip AI Assistant) — Development Guidelines

Last updated: 2026-04-22

## What This Project Is

ChitoGo is an AI-powered Taipei travel assistant. Users describe trip preferences (or speak Taiwanese Mandarin), and the agent returns a personalized day itinerary. The system is composed of three independent FastAPI microservices plus a Vue 3 frontend.

## Services & Ports

| Service | Directory | Port | Purpose |
|---------|-----------|------|---------|
| Place Data Service | `backend/Chitogo_DataBase/` | 8000 | PostgreSQL store for Taipei venues; search, nearby, recommend APIs |
| Itinerary Planner | `backend/app/` | 8000* | SQLite-based planner; scores and orders venues into a day plan |
| Chat Agent | `backend/Chat_Agent/` | 8100 | LLM orchestration layer; session management; calls Data Service |
| Speech API | `backend/taiwanese_speech/` | — | Taiwanese speech-to-text via Hugging Face endpoint |
| Frontend | `frontend/` | 5173 | Vue 3 + Vite SPA |

*Itinerary Planner and Data Service share the same default port — run only one at a time unless ports are overridden.

## Tech Stack

- **Backend**: Python 3.11, FastAPI 0.111, Pydantic v2, uvicorn
- **LLM**: Gemini 2.5 Flash (primary), Claude Sonnet 4.6 (fallback), OpenRouter GPT-4.1-mini (alternative)
- **Databases**: SQLite (Itinerary Planner via aiosqlite), PostgreSQL (Data Service via SQLAlchemy 2.x)
- **External APIs**: Google Places API (New), OpenWeatherMap, Google Maps (routing), Hugging Face (ASR)
- **Frontend**: Vue 3, TypeScript 5.x, Vite 5, Axios

## Commands

```bash
# Install everything
make install                         # pip install backend/requirements.txt + npm install frontend/

# Run services individually
make backend                         # Itinerary Planner on :8000
make frontend                        # Vue dev server on :5173
make dev                             # Both concurrently

# Chat Agent (separate service)
cd backend/Chat_Agent && uvicorn app.main:app --reload --port 8100

# Data Service
cd backend/Chitogo_DataBase && uvicorn app.main:app --reload --port 8000

# Tests
cd backend && pytest
cd backend/Chat_Agent && pytest
cd backend/Chitogo_DataBase && pytest

# Lint
ruff check .
```

## Environment Setup

Each service has its own `.env.example`. Copy and fill in:

```bash
cp backend/.env.example backend/.env              # Itinerary Planner
cp backend/Chat_Agent/.env.example backend/Chat_Agent/.env
cp backend/Chitogo_DataBase/.env.example backend/Chitogo_DataBase/.env
cp backend/taiwanese_speech/.env.example backend/taiwanese_speech/.env
```

Key variables for Chat Agent: `LLM_PROVIDER`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `DATA_SERVICE_BASE_URL=http://localhost:8000`

## Project Layout

```
backend/
├── app/                    # Itinerary Planner service (SQLite)
│   ├── main.py             # FastAPI app + lifespan
│   ├── api/v1/router.py    # Route definitions
│   ├── models/             # SQLAlchemy models + Pydantic schemas
│   ├── services/           # Itinerary builder, scoring, routing
│   ├── providers/          # Google Places, crawler, cache aggregator
│   └── data/venues.json    # Seed data for local DB
├── Chat_Agent/             # LLM Agent orchestration service
│   └── app/
│       ├── main.py         # App factory (create_app)
│       ├── chat/           # Message handler, trace store
│       ├── session/        # Session store + TTL sweeper
│       └── tools/          # Tool registry, place/route adapters
├── Chitogo_DataBase/       # Place Data Service (PostgreSQL)
│   └── app/
│       ├── main.py
│       ├── db.py           # SQLAlchemy engine + base
│       ├── models/         # ORM models
│       ├── routers/        # health, places, retrieval
│       └── services/       # ingestion, category
├── taiwanese_speech/       # Speech-to-text module (Hugging Face)
└── scripts/                # social_crawler.py, test_asrapi.py

frontend/
└── src/
    ├── App.vue
    ├── main.ts
    ├── pages/HomePage.vue
    ├── services/api.ts     # Axios API client
    └── types/itinerary.ts
```

## Code Style

- Python: PEP 8, type annotations on all functions, async/await throughout
- TypeScript: strict mode, PascalCase components, camelCase hooks/utils
- Error handling: raise `ValueError("code: message")` for domain errors; FastAPI handler converts to 400
- No `print()` — use `logging` (Python) or structured logs

## Testing Conventions

- Framework: `pytest` + `pytest-asyncio`
- Test files: `tests/test_*.py`
- Fake LLM fixture: `backend/Chat_Agent/tests/fake_llm.py`
- Run with coverage: `pytest --cov=app --cov-report=term-missing`

## Git Conventions

- Branch naming: `NNN-feature-description` (e.g. `005-fix-district-extraction`)
- Commit style: imperative short description (no conventional-commit prefix enforced)
- PRs merged from feature branches into `main`
