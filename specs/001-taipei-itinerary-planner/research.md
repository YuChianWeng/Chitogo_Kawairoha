# Research: Taipei AI Itinerary Planner

**Branch**: `001-taipei-itinerary-planner` | **Date**: 2026-03-29

All technical decisions documented below. No NEEDS CLARIFICATION markers remain.

---

## Decision 1: Frontend Framework — Vue 3 over React

**Decision**: Vue 3 with Composition API and Vite 5

**Rationale**: For a hackathon with a tight timeline, Vue 3 requires less boilerplate than React for a form + display layout. Vite's dev server starts in under 300 ms. Vue's single-file components keep template, logic, and style co-located, reducing context-switching during rapid iteration. The component surface area is small (4 components), so framework differences in scalability are irrelevant.

**Alternatives considered**:
- React + Vite: Equally valid; slightly more boilerplate for state management. Use if team has stronger React background.
- Svelte: Excellent for hackathon size, but less team familiarity and fewer UI component libraries.
- Plain HTML/JS: Viable for MVP, but loses reactivity for loading states and dynamic card rendering.

---

## Decision 2: Backend Framework — FastAPI

**Decision**: FastAPI 0.111 with Python 3.11

**Rationale**: FastAPI provides automatic OpenAPI docs, Pydantic v2 integration for request/response validation, and async support. Route definition for a single primary endpoint is minimal. Python 3.11's performance improvements over 3.10 reduce overhead on the synchronous scoring path. The team's likely familiarity with Python makes this the lowest-friction choice.

**Alternatives considered**:
- Flask: Synchronous, no built-in validation. More setup to reach the same correctness level.
- Django REST Framework: Too much overhead for a single endpoint MVP.
- Express (Node): Would require a Node backend alongside a Node frontend, possible, but team likely Python-first.

---

## Decision 3: Data Storage — SQLite with JSON Seed Bootstrap

**Decision**: SQLite via `aiosqlite` for venue data; `venues.json` as the authoritative seed source

**Rationale**: SQLite requires zero infrastructure — no running server, no connection pooling — and is included in Python's stdlib. Venue data is read-heavy and small (~80 rows). `venues.json` serves as the source of truth that can be edited by hand before the demo. On startup, `main.py` checks if the DB is empty and seeds from JSON. The enrichment cache (for optional crawler module) also lives in SQLite as a separate table.

**Alternatives considered**:
- Pure in-memory JSON: No persistence between restarts; fine for a demo but harder to query with filters.
- PostgreSQL: Unnecessary operational complexity for hackathon scale.
- MongoDB: Schema flexibility not needed; venues have a fixed structure.

---

## Decision 4: Weather API — OpenWeatherMap Current Weather

**Decision**: OpenWeatherMap Free Tier — `GET /data/2.5/weather?q=Taipei,TW`

**Rationale**: Free tier allows 1,000 calls/day, more than sufficient for a demo. The response includes `weather[0].main` (Clear/Clouds/Rain/Drizzle/Thunderstorm), `main.temp`, and `pop` (precipitation probability in forecast). Setup requires one API key with no credit card needed. The API is reliable and well-documented.

**Caching**: Results are cached in-process (dict + timestamp) for 30 minutes. This eliminates redundant calls during demo load-testing and protects against rate limits.

**Fallback**: On any error (timeout, 401, 429, network failure), the service returns `WeatherContext(condition="unknown", temperature_c=None, precipitation_pct=None)`. The scoring engine applies neutral weather weights (0.85) and the UI omits the weather badge silently.

**Alternatives considered**:
- WeatherAPI.com: Also free, similar endpoint. Either works; OpenWeatherMap has slightly wider community documentation.
- Open-Meteo: Fully free, no API key needed. Viable backup option.
- Taiwan CWA (Central Weather Administration): Has official Taipei data but requires Chinese-language API navigation and CORS restrictions.

---

## Decision 5: Recommendation Engine — Rule-Based Scoring (No LLM for Core)

**Decision**: Deterministic weighted scoring formula; LLM optional for explanation text only

**Rationale**: Rule-based scoring is fast (< 1 ms for 80 venues), debuggable, and fully controllable during a demo. The scoring weights (interest 40%, weather 30%, trend 20%, budget 10%) were chosen based on the product spec's priority ordering. An LLM is not needed to produce a good itinerary — only to produce a richer explanation sentence. This keeps the critical path free of LLM latency and API key dependencies.

**LLM optional path**: When `USE_LLM=true` in `.env`, each stop's reason is generated via a single LLM prompt. This is parallelized across stops with a 2-second per-stop timeout. The system falls back to templates on any failure.

**Alternatives considered**:
- Full LLM pipeline (LLM selects venues): Non-deterministic, slow (~5–10 s for selection + explanation), costly, and hard to control for demo stability.
- Vector similarity search: Overkill for 80 venues. Useful at 10,000+ venues.
- Collaborative filtering: Requires user interaction data that doesn't exist yet.

---

## Decision 6: Route Optimization — Greedy Nearest-Neighbor

**Decision**: Greedy nearest-neighbor with score × proximity weighting

**Rationale**: For 3–5 stops from a pool of ~80 candidates, greedy NN produces near-optimal routes in O(n) per stop. True TSP is unnecessary at this scale and adds no perceptible quality improvement for the user. The combined score × proximity weight prevents the algorithm from always picking the geographically nearest venue when a significantly better-scored venue is only slightly farther away.

**Alternatives considered**:
- True TSP (held-karp): O(n²·2ⁿ), unnecessary for n ≤ 80.
- Cluster-then-rank: Viable; semantically similar but more implementation surface area.
- Random sampling: Non-deterministic, harder to explain to demo judges.

---

## Decision 7: Seed Venue Dataset

**Decision**: Manually curated `venues.json` with ~80 venues across 8 districts

**Target distribution**:
- Districts: Da'an, Zhongzheng, Wanhua, Zhongshan, Xinyi, Shilin, Beitou, Songshan
- Categories: café (20%), restaurant (20%), museum/gallery (15%), market/shopping (15%), park/outdoor (15%), temple/heritage (10%), nightlife (5%)
- Indoor/outdoor split: ~60% indoor, ~40% outdoor
- Cost levels: 40% cheap, 45% mid, 15% upscale
- Each venue includes: name (English), district, category, tags (3–5), lat/lon, indoor flag, cost_level (1–3), avg_dwell_minutes, trend_score (0–1), open_hours (start/end)

**Crawler enrichment module** (optional, post-MVP): A background task that fetches trending venues from social sources (e.g., Google Trends Taipei searches, Instagram location tags) and updates `trend_score` in the SQLite enrichment cache. The main scoring engine reads from this cache if available, otherwise uses the seed `trend_score`. This is implemented as a standalone script that can be run manually or on a cron schedule.

**Fallback when crawler unavailable**: Seed `trend_score` values are pre-assigned based on known popularity (e.g., Shilin Night Market = 0.95, local café = 0.40). The scoring engine works identically regardless of whether crawler data has updated these values.

---

## Decision 8: TypeScript for Frontend

**Decision**: TypeScript 5.x throughout the frontend

**Rationale**: The API contract is typed; sharing those types with the frontend prevents silent mismatches during rapid iteration. Vite + Vue 3 supports TypeScript out of the box. The type surface is small (one request type, one response type), so the overhead is low.

---

## Resolved Unknowns Summary

| Item | Resolution |
|------|-----------|
| Frontend framework | Vue 3 + Vite |
| Backend framework | FastAPI 0.111 / Python 3.11 |
| Storage | SQLite (aiosqlite) + venues.json seed |
| Weather source | OpenWeatherMap Free Tier |
| Recommendation approach | Rule-based scoring, LLM optional |
| Route algorithm | Greedy nearest-neighbor |
| Venue data source | Hand-curated seed + optional crawler enrichment |
| LLM integration | Optional toggle (USE_LLM=false for MVP) |
