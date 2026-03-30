# Taipei Trip Agent

A same-day itinerary planner for Taipei tourists. Enter your preferences — district, time range, interests, budget, and travel companions — and get a personalized 3-5 stop itinerary with weather-aware recommendations and optimized routing.

## Features

- **Dynamic venue fetching** — candidates pulled at request time from Google Places API and crawler/social sources
- **Personalized itineraries** based on interests, budget, and companion type
- **Weather-aware scoring** — prioritizes indoor venues on rainy days, outdoor on clear days
- **Route optimization** via greedy nearest-neighbor algorithm (minimizes travel time)
- **Smart merge & dedup** — results from multiple sources are normalized, merged, and deduplicated
- **In-memory TTL cache** — repeat queries served instantly without redundant API calls
- **Graceful fallback** — if external sources fail, falls back to 35 curated local venues
- **Fast** — itineraries generated in under 10 seconds

## Architecture

```
Browser (Vue 3 SPA)
    |  POST /api/v1/itinerary
    v
FastAPI ──────────────────────────────────────────────
    |
    ├── Candidate Providers (parallel fetch)
    |     ├── Google Places API (New) ──┐
    |     ├── Crawler / Social API ─────┤→ normalize → merge/dedup → filter
    |     └── Local seed (fallback) ────┘
    |
    ├── ScoringEngine
    |     └── score = interest(40%) + weather(30%) + trend(20%) + budget(10%)
    |
    ├── RouteOptimizer
    |     └── Greedy nearest-neighbor with time budget
    |
    └── ItineraryBuilder
          └── Assemble response with reasons
```

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, FastAPI 0.111, Pydantic v2, httpx |
| Frontend | Vue 3, Vite 5, TypeScript 5, Axios |
| Data Sources | Google Places API, Crawler API, local SQLite seed |
| Weather | OpenWeatherMap API (free tier) |
| Cache | In-memory TTL (candidates: 5 min, weather: 30 min) |

## Prerequisites

- Python 3.11+
- Node.js 20+
- Google Places API key ([Google Cloud Console](https://console.cloud.google.com/apis/credentials)) — enable "Places API (New)"
- OpenWeatherMap API key ([get one free](https://openweathermap.org/api)) — optional, for weather integration

## Setup

### Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your API keys
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
| `GOOGLE_PLACES_API_KEY` | (empty) | Google Places API key for live venue fetching |
| `CRAWLER_API_URL` | (empty) | Crawler/social source endpoint URL |
| `CANDIDATE_CACHE_TTL_MINUTES` | `5` | Cache duration for external candidate results |
| `OPENWEATHER_API_KEY` | (empty) | OpenWeatherMap API key for weather integration |
| `MOCK_WEATHER` | (empty) | Override weather for demos: `rain`, `clear`, `cloudy` |
| `USE_LLM` | `false` | Enable LLM-based reason generation (stretch goal) |
| `DB_PATH` | `./taipei.db` | SQLite database path (seed/fallback data) |
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
  "date": "2026-03-30",
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

List seeded venues (debug endpoint).

## Scoring

Venues are ranked by a weighted score:

| Factor | Weight | Description |
|--------|--------|-------------|
| Interest match | 40% | How well the venue's tags match selected interests |
| Weather suitability | 30% | Indoor/outdoor preference adjusted for current weather |
| Trend score | 20% | Venue popularity signal (0.0-1.0) |
| Budget compatibility | 10% | Venue cost level vs. user budget |

## Data Flow

1. **Fetch** — Google Places + Crawler queried in parallel (cached results used when available)
2. **Normalize** — External results mapped to internal `Venue` schema, districts assigned from coordinates
3. **Merge & Dedup** — Combined by name similarity and 50m proximity; trend scores merged (max)
4. **Filter** — District proximity, indoor preference, cost level (relaxed progressively if < 3 results)
5. **Fallback** — If external sources return < 3 venues, local seed data fills the gap
6. **Score** — Weighted scoring: interest + weather + trend + budget
7. **Route** — Greedy nearest-neighbor ordering within time budget
8. **Respond** — Assembled itinerary with arrival times, durations, and reasons

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
│   ├── providers/
│   │   ├── base.py           # CandidateProvider protocol, helpers
│   │   ├── google_places.py  # Google Places API (New) provider
│   │   ├── crawler.py        # Crawler/social source provider
│   │   ├── cache.py          # In-memory TTL cache
│   │   └── aggregator.py     # Merge, dedup, fallback orchestrator
│   ├── models/
│   │   ├── db.py             # SQLite access, Venue entity, seeding
│   │   └── schemas.py        # Pydantic request/response models
│   ├── services/
│   │   ├── scoring.py        # Venue scoring engine
│   │   ├── routing.py        # Route optimizer
│   │   └── itinerary_builder.py  # Pipeline orchestrator
│   └── data/
│       └── venues.json       # 35 curated Taipei venues (fallback)
frontend/
├── src/
│   ├── pages/HomePage.vue    # Main page (form + results)
│   ├── services/api.ts       # Axios API client
│   └── types/itinerary.ts    # TypeScript interfaces
specs/                        # Feature specs and implementation plans
```
