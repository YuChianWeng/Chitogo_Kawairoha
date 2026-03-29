# Taipei Trip Agent

A same-day itinerary planner for Taipei tourists. Enter your preferences — district, time range, interests, budget, and travel companions — and get a personalized 3–5 stop itinerary with weather-aware recommendations and optimized routing.

## Features

- **Personalized itineraries** based on interests, budget, and companion type
- **Weather-aware scoring** — prioritizes indoor venues on rainy days, outdoor on clear days
- **Route optimization** via greedy nearest-neighbor algorithm (minimizes travel time)
- **35 curated venues** across 12 Taipei districts
- **Template-based reasons** explaining why each stop was selected
- **Fast** — itineraries generated in under 10 seconds

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, FastAPI 0.111, aiosqlite, Pydantic v2 |
| Frontend | Vue 3, Vite 5, TypeScript 5, Axios |
| Database | SQLite (seeded from `venues.json` on startup) |
| Weather | OpenWeatherMap API (free tier) |

## Prerequisites

- Python 3.11+
- Node.js 20+
- OpenWeatherMap API key ([get one free](https://openweathermap.org/api))

## Setup

### Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OPENWEATHER_API_KEY
```

### Frontend

```bash
cd frontend
npm install
```

## Running

**Using Make (recommended):**

```bash
make dev        # Start both backend and frontend concurrently
```

**Or manually in two terminals:**

```bash
# Terminal 1 — backend (http://localhost:8000)
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (http://localhost:5173)
cd frontend && npm run dev
```

Open http://localhost:5173 in your browser.

API docs are available at http://localhost:8000/docs.

## Environment Variables

Create `backend/.env` from `backend/.env.example`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENWEATHER_API_KEY` | (required) | OpenWeatherMap API key |
| `MOCK_WEATHER` | (empty) | Override weather for demos: `rain`, `clear`, `cloudy` |
| `USE_LLM` | `false` | Enable LLM-based reason generation (stretch goal) |
| `DB_PATH` | `./taipei.db` | SQLite database path |
| `WEATHER_CACHE_TTL_MINUTES` | `30` | Weather cache duration in minutes |

## API

### `POST /api/v1/itinerary`

Generate a personalized itinerary.

**Request body:**

```json
{
  "district": "Da'an",
  "start_time": "10:00",
  "end_time": "18:00",
  "interests": ["culture", "food", "cafe"],
  "budget": "medium",
  "companion": "couple",
  "indoor_pref": "both"
}
```

**Response:**

```json
{
  "status": "ok",
  "district": "Da'an",
  "date": "2026-03-29",
  "weather_condition": "clear",
  "stops": [
    {
      "order": 1,
      "venue_id": "v001",
      "name": "National Palace Museum",
      "district": "Shilin",
      "category": "museum",
      "suggested_start": "10:00",
      "suggested_end": "12:00",
      "duration_minutes": 120,
      "travel_minutes_from_prev": 0,
      "reason": "A popular indoor museum perfect for exploring Taiwanese history...",
      "tags": ["culture", "history", "art"],
      "cost_level": "low",
      "indoor": true
    }
  ],
  "total_stops": 3,
  "total_duration_minutes": 360
}
```

**Valid field values:**
- `district`: `Zhongzheng`, `Da'an`, `Zhongshan`, `Xinyi`, `Wanhua`, `Songshan`, `Neihu`, `Shilin`, `Beitou`, `Wenshan`, `Nangang`, `Datong`
- `budget`: `low`, `medium`, `high`
- `companion`: `solo`, `couple`, `family`, `friends`
- `indoor_pref`: `indoor`, `outdoor`, `both`
- `interests`: `food`, `culture`, `shopping`, `nature`, `nightlife`, `art`, `history`, `cafe`, `sports`, `temple`

### `GET /api/v1/health`

Liveness check.

### `GET /api/v1/venues`

List all seeded venues (debug endpoint).

## Scoring

Venues are ranked by a weighted score:

| Factor | Weight | Description |
|--------|--------|-------------|
| Interest match | 40% | How well the venue's tags match selected interests |
| Weather suitability | 30% | Indoor/outdoor preference adjusted for current weather |
| Trend score | 20% | Venue popularity signal (0.0–1.0) |
| Budget compatibility | 10% | Venue cost level vs. user budget |

## Venue Data

Venue data lives in `backend/app/data/venues.json` and is seeded into SQLite on first startup. To reset the database with updated venue data:

```bash
rm backend/taipei.db
# Restart the backend
```

## Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

## Project Structure

```
backend/
├── app/
│   ├── main.py               # App factory, CORS, DB init
│   ├── config.py             # Settings (pydantic-settings)
│   ├── api/v1/
│   │   ├── itinerary.py      # POST /itinerary handler
│   │   └── router.py
│   ├── models/
│   │   ├── db.py             # SQLite access, Venue entity, seeding
│   │   └── schemas.py        # Pydantic request/response models
│   ├── services/
│   │   ├── scoring.py        # Venue scoring engine
│   │   ├── routing.py        # Route optimizer
│   │   └── itinerary_builder.py  # Pipeline orchestrator
│   └── data/
│       └── venues.json       # 35 curated Taipei venues
frontend/
├── src/
│   ├── pages/HomePage.vue    # Main page (form + results)
│   ├── services/api.ts       # Axios API client
│   └── types/itinerary.ts    # TypeScript interfaces
specs/                        # Feature specs and implementation plans
```
