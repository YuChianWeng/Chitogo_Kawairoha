# Developer Quickstart: ChitoGO PRD Wizard

This guide covers the minimal setup to run and test the PRD wizard feature on branch `011-chitogo-prd-wizard`.

---

## Prerequisites

- Python 3.11
- Node.js 18+
- Docker (for PostgreSQL Data Service) or an existing Data Service running on :8000
- API keys: `GEMINI_API_KEY` (primary LLM), `GOOGLE_MAPS_API_KEY` (routing)

---

## 1. Install New Dependencies

```bash
# Backend — add rapidfuzz and odfpy to Chat Agent
cd backend/Chat_Agent
pip install rapidfuzz>=3.0 odfpy>=1.4

# Frontend — add vue-router
cd frontend
npm install vue-router@4
```

---

## 2. Environment Setup

```bash
# Copy and fill Chat Agent .env
cp backend/Chat_Agent/.env.example backend/Chat_Agent/.env
```

Key variables for the wizard:

```env
# Required
GEMINI_API_KEY=your_gemini_key
GOOGLE_MAPS_API_KEY=your_maps_key
DATA_SERVICE_BASE_URL=http://localhost:8000

# ODS hotel data path (absolute or relative to Chat Agent working dir)
HOTEL_ODS_PATH=../../旅宿列表匯出_20260425103741.ods

# Optional (defaults shown)
ROUTE_PROVIDER=google_maps      # set to "fallback" to skip Maps API calls
REACHABILITY_CONCURRENCY=5      # max concurrent route API calls
REACHABLE_CACHE_TTL_SEC=300     # 5-minute TTL for reachable venue cache
```

---

## 3. Start Services

### Data Service (PostgreSQL + Place API)
```bash
cd backend/Chitogo_DataBase
uvicorn app.main:app --reload --port 8000
```

### Chat Agent (Trip wizard endpoints)
```bash
cd backend/Chat_Agent
uvicorn app.main:app --reload --port 8100
```

### Frontend
```bash
cd frontend
npm run dev
# → http://localhost:5173
```

Or run all at once:
```bash
make dev   # starts Itinerary Planner + Frontend; start Chat Agent separately
```

---

## 4. Verify Trip Endpoints

```bash
# 1. Create a session
curl -s -X POST http://localhost:8100/api/v1/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{}' | jq .session_id

# Store result: SESSION_ID=<value>

# 2. Submit quiz
curl -s -X POST http://localhost:8100/api/v1/trip/quiz \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'$SESSION_ID'",
    "answers": {"Q1":"A","Q2":"A","Q3":"A","Q4":"A","Q5":"B","Q6":"A","Q7":"A","Q8":"A","Q9":"B"}
  }' | jq .

# 3. Submit setup
curl -s -X POST http://localhost:8100/api/v1/trip/setup \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'$SESSION_ID'",
    "accommodation": {"booked": false, "district": "大安區"},
    "transport": {"modes": ["walk", "transit"], "max_minutes_per_leg": 30}
  }' | jq .

# 4. Get candidates (near Taipei 101)
curl -s "http://localhost:8100/api/v1/trip/candidates?session_id=$SESSION_ID&lat=25.0339&lng=121.5645" | jq .
```

---

## 5. Run Tests

```bash
# Backend — trip endpoints and services
cd backend/Chat_Agent
pytest tests/test_trip.py tests/test_gene_classifier.py tests/test_reachability.py -v

# All Chat Agent tests
pytest --cov=app --cov-report=term-missing

# Frontend
cd frontend
npm run test
```

---

## 6. Frontend Wizard Flow

Open http://localhost:5173 — the app redirects to `/quiz`:

1. **`/quiz`** — Complete 9 questions → see travel gene card → navigate to `/setup`
2. **`/setup`** — Enter accommodation details (hotel name or district + budget), set optional return time, choose transport modes → navigate to `/trip`
3. **`/trip`** — Core loop: see 6 venue cards → tap one → navigation screen → tap "我到了！" → rate 1–5★ → repeat
4. **`/summary`** — Tap "我想回家" at any time to view journey timeline

---

## 7. Key File Locations (new files)

| File | Purpose |
|------|---------|
| `backend/Chat_Agent/app/api/v1/trip.py` | 8 trip endpoints |
| `backend/Chat_Agent/app/orchestration/gene_classifier.py` | Travel gene scoring |
| `backend/Chat_Agent/app/services/reachability.py` | Haversine pre-filter + route estimation |
| `backend/Chat_Agent/app/services/candidate_picker.py` | 6-candidate selection + demand mode |
| `backend/Chat_Agent/app/services/go_home_advisor.py` | "該回家了" time calculation |
| `frontend/src/router/index.ts` | Vue Router setup |
| `frontend/src/types/trip.ts` | TypeScript type definitions |
| `frontend/src/pages/QuizPage.vue` | 9-question preference quiz |
| `frontend/src/pages/SetupPage.vue` | Accommodation + transport setup |
| `frontend/src/pages/TripPage.vue` | Main recommendation loop |
| `frontend/src/pages/SummaryPage.vue` | Journey summary |
| `frontend/src/components/CandidateGrid.vue` | 6-card venue grid |
| `frontend/src/components/DemandModal.vue` | "None of these" free-text demand |
| `frontend/src/components/NavigationPanel.vue` | Post-selection navigation screen |
| `frontend/src/components/RatingCard.vue` | Post-arrival star rating |

---

## 8. Development Notes

- **State machine errors**: If you get `state_error:*` during development, check the session's `flow_state` via the existing chat session debug endpoint or by inspecting session store directly.
- **LLM fallback**: Set `ROUTE_PROVIDER=fallback` in `.env` to skip Google Maps calls during development; haversine estimates will be used instead.
- **Hotel validation**: The wizard calls the Data Service `/api/v1/lodgings/check` and `/api/v1/lodgings/candidates` endpoints; ensure the Data Service is seeded with the ODS data via the ingestion script.
- **Go-home polling**: The frontend polls every 60 s; to test the reminder in development, set `return_time` to the current time + 2 minutes in the setup form.
