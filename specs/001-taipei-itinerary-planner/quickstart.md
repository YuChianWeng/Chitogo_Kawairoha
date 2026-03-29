# Quickstart: Taipei AI Itinerary Planner

**Branch**: `001-taipei-itinerary-planner`

Get both services running locally in under 5 minutes.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | `pyenv install 3.11` or system package |
| Node.js | 20+ | `nvm install 20` or system package |
| Git | any | system package |

You also need an OpenWeatherMap API key (free at openweathermap.org — takes ~2 minutes to register).

---

## 1. Clone & Configure

```bash
git clone <repo-url>
cd Taipei-Trip-agent
```

---

## 2. Backend Setup

```bash
cd backend

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set OPENWEATHER_API_KEY=<your-key>
```

**`.env` file**:
```env
OPENWEATHER_API_KEY=your_key_here
USE_LLM=false
DATABASE_URL=sqlite+aiosqlite:///./taipei.db
WEATHER_CACHE_TTL_MINUTES=30
```

```bash
# Start the backend (seeds DB from venues.json on first run)
uvicorn app.main:app --reload --port 8000
```

Backend is live at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## 3. Frontend Setup

Open a second terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend is live at `http://localhost:5173`. It proxies API calls to `http://localhost:8000`.

---

## 4. Verify Everything Works

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Generate a test itinerary
curl -s -X POST http://localhost:8000/api/v1/itinerary \
  -H "Content-Type: application/json" \
  -d '{"district":"daan","start_time":"10:00","end_time":"14:00","interests":["food","cafes"],"budget":"mid","companion":"solo","indoor_pref":"no_preference"}' \
  | python3 -m json.tool
```

Expected: a JSON response with `total_stops` between 3 and 5.

---

## 5. Run Tests

```bash
# Backend
cd backend
source .venv/bin/activate
pytest tests/ -v

# Frontend
cd frontend
npm run test
```

---

## 6. Optional: Enable LLM Explanations

```env
# In backend/.env
USE_LLM=true
LLM_API_KEY=<anthropic-or-openai-key>
LLM_PROVIDER=anthropic        # or: openai
LLM_MODEL=claude-haiku-4-5-20251001
LLM_TIMEOUT_SECONDS=2
```

Restart the backend after changing `.env`. Explanations will be richer; generation time increases by ~2 s per stop (parallelized).

---

## 7. Optional: Run Crawler Enrichment

Updates `trend_score` values from social sources (requires separate API keys):

```bash
cd backend
python -m app.scripts.enrich_venues
```

This is a one-shot script. Run it before the demo to update venue trend scores.

---

## Development Tips

- **Hot reload**: Both `uvicorn --reload` and `vite dev` watch for file changes automatically.
- **Edit venue data**: Modify `backend/app/data/venues.json`, then delete `taipei.db` and restart the backend to re-seed.
- **Simulate rainy weather**: Set `MOCK_WEATHER=rain` in `.env` to bypass the real weather API and always return rain. Useful for demo preparation.
- **API docs**: `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc`
- **Debug scoring**: Call `GET /api/v1/venues?district=daan` to inspect the seed data for a district.

---

## Project Structure Quick Reference

```
backend/app/
├── main.py                  ← FastAPI entry point, DB seed, CORS
├── api/v1/itinerary.py      ← POST /api/v1/itinerary handler
├── services/weather.py      ← OpenWeatherMap + cache + fallback
├── services/scoring.py      ← Rule-based venue scoring
├── services/routing.py      ← Greedy nearest-neighbor optimizer
├── services/itinerary_builder.py  ← Assembly + reason generation
├── models/schemas.py        ← All Pydantic types
├── models/db.py             ← SQLite access layer
└── data/venues.json         ← Seed venue dataset

frontend/src/
├── components/PreferenceForm.vue   ← Input form
├── components/ItineraryDisplay.vue ← Output cards container
├── components/StopCard.vue         ← Single stop card
├── components/WeatherBadge.vue     ← Weather indicator
├── pages/HomePage.vue              ← Root page
├── services/api.ts                 ← Axios API client
└── types/itinerary.ts              ← TypeScript types
```
