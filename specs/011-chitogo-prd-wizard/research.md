# Research: ChitoGO PRD State-Machine Trip Wizard

**Phase 0 output** — all NEEDS CLARIFICATION items resolved

---

## 1. ODS Hotel Data Parsing

**Decision**: Parse `旅宿列表匯出_20260425103741.ods` at Chat Agent startup using the `odfpy` library (already available in the Data Service virtualenv). Parse via `xml.etree.ElementTree` over the ZIP-embedded `content.xml`; no `pandas` dependency needed. Load all records into an in-memory list of `LegalLodging` dicts indexed by normalized name at application start.

**Rationale**: The ODS file is 71 KB (~a few hundred rows, fast to parse). Startup-time load means zero I/O per request. The Data Service already has a `LegalLodging` PostgreSQL model and `lodging_search.py` service — the Chat Agent's `PlaceToolAdapter` already exposes `check_lodging_legal_status` and `search_lodging_candidates` endpoints. Therefore hotel validation should be delegated to the Data Service rather than duplicated.

**ODS columns confirmed** (row 0):
`核准登記營業日期, 縣市旅宿登記證號, 類別, 標章, 溫泉標章, 旅宿名稱[5], 縣市[6], 鄉鎮[7], 郵遞區號, 地址`

**Alternatives considered**:
- `pandas` + `odfpy` engine: heavier dependency, unnecessary for simple row extraction.
- Loading into PostgreSQL via migration: already done in the Data Service; Chat Agent should call the Data Service rather than maintain a second copy.

---

## 2. Fuzzy Hotel Name Matching

**Decision**: Use `rapidfuzz` (Levenshtein/token-set ratio) with threshold 85+ for valid match, 60–84 for fuzzy suggestion. Add `rapidfuzz>=3.0` to `backend/Chat_Agent/requirements.txt` (or the Data Service requirements if matching is done there).

**Rationale**: `rapidfuzz` is 20–100× faster than pure Python `difflib`, handles Chinese characters correctly via Unicode normalization, and is actively maintained. The Data Service's `lodging_search.py` likely already implements similar logic; if so, the Chat Agent simply proxies through `PlaceToolAdapter`.

**Alternatives considered**:
- `difflib.SequenceMatcher`: pure Python, sufficient for small dataset but no token-set ratio support (important for Chinese hotel names with varied word order).
- `thefuzz` (fuzzywuzzy): wrapper around Levenshtein with optional C extension; `rapidfuzz` is a drop-in replacement that is faster and better maintained.

---

## 3. Travel Gene Scoring Matrix

**Decision**: Deterministic heuristic matrix — Q1–Q9 answers each add integer points to gene dimension scores; highest score wins. Tiebreaker (within 1 point): use LLM to decide based on full answer set; if LLM unavailable, favor the gene with the earlier Q tie-break answer.

**Scoring matrix** (answer → gene points, questions phrased in app UI):

| Q | Topic | A → genes (+1) | B → genes (+1) | C → genes (+1) |
|---|-------|----------------|----------------|----------------|
| Q1 | 偏好環境 | 文清, 親子 | 野外, 一日 | 夜貓子 |
| Q2 | 旅遊節奏 | 文清 | 一日 | — |
| Q3 | 人群偏好 | 文清, 不常來 | 親子, 夜貓子 | — |
| Q4 | 同行對象 | 文清, 夜貓子 | 親子 | — |
| Q5 | 飲食傾向 | 不常來, 夜貓子 | 文清, 親子 | — |
| Q6 | 活躍時段 | 一日, 不常來 | 夜貓子 | — |
| Q7 | 體驗類型 | 文清 | 野外, 親子 | — |
| Q8 | 移動方式 | 野外, 文清 | 一日, 不常來 | — |
| Q9 | 台北熟悉度 | 不常來 | 夜貓子, 文清 | — |

Maximum possible score per gene ≈ 4–5. All 6 genes start at 0.

**Gene → mascot mapping** (preliminary; product to confirm illustrations):
| Gene | Mascot ID |
|------|-----------|
| 文清 | wenqing_cat |
| 親子 | family_bear |
| 不常來 | tourist_owl |
| 夜貓子 | night_fox |
| 一日 | daytrip_rabbit |
| 野外 | outdoor_deer |

**Alternatives considered**:
- LLM-only classification: non-deterministic, slow, expensive per quiz; heuristic matrix is instant and fully testable.
- Survey-validated weights: ideal but out of scope for v1; matrix can be updated without API contract changes.

---

## 4. Session State Machine Extension Strategy

**Decision**: Add new PRD fields to the existing `Session` Pydantic model in `session/models.py` as optional fields with sensible defaults. Existing chat endpoints that don't set `flow_state` simply see it as `QUIZ` (the default) and continue to work unchanged.

**State transitions**:
```
[new session]  →  QUIZ
QUIZ           →  TRANSPORT   (POST /trip/quiz succeeds)
TRANSPORT      →  RECOMMENDING (POST /trip/setup succeeds)
RECOMMENDING   →  RATING      (POST /trip/select + "我到了！" confirmed)
RATING         →  RECOMMENDING (POST /trip/rate succeeds)
RECOMMENDING   →  ENDED       (POST /trip/summary triggered by "我想回家")
RATING         →  ENDED       (same "我想回家" path)
```

**FSM guard table**:
| Endpoint | Allowed states | Rejection error |
|----------|---------------|-----------------|
| POST /trip/quiz | QUIZ | `state_error:expected_QUIZ` |
| POST /trip/setup | TRANSPORT | `state_error:expected_TRANSPORT` |
| GET /trip/candidates | RECOMMENDING | `state_error:expected_RECOMMENDING` |
| POST /trip/select | RECOMMENDING | `state_error:expected_RECOMMENDING` |
| POST /trip/rate | RATING | `state_error:expected_RATING` |
| POST /trip/demand | RECOMMENDING | `state_error:expected_RECOMMENDING` |
| GET /trip/should_go_home | RECOMMENDING, RATING | `state_error:not_in_trip` |
| GET /trip/summary | RECOMMENDING, RATING, ENDED | `state_error:trip_not_started` |

**Alternatives considered**:
- Separate PRD session model: cleaner isolation but requires session store changes and new session IDs for wizard sessions; too disruptive to existing chat.
- Redis-backed sessions: unnecessary for v1 scale; in-memory store with TTL sweeper is sufficient.

---

## 5. Frontend Routing Architecture

**Decision**: Add `vue-router@4` to `frontend/package.json`. Create `frontend/src/router/index.ts` with named routes `/quiz`, `/setup`, `/trip`, `/summary`. Session ID and travel gene are stored in `localStorage` keyed by `chitogo_session_id` and `chitogo_gene`. The router guard checks localStorage on each route entry; `/trip` and `/setup` redirect to `/quiz` if no session ID.

**Rationale**: vue-router is the standard Vue 3 routing solution; no alternative is viable for a multi-page wizard.

**Route guards**:
- `/quiz`: always accessible; creates new session on load
- `/setup`: requires `chitogo_session_id` in localStorage
- `/trip`: requires `chitogo_session_id` and `chitogo_gene` in localStorage
- `/summary`: requires `chitogo_session_id`

---

## 6. Candidate Recommendation Performance

**Decision**: Haversine pre-filter at 1.5× the walking radius equivalent of `max_minutes_per_leg` (at 4.5 km/h). This reduces the candidate pool from hundreds to ~20–50 venues before calling Google Maps. Use `asyncio.gather` with a `asyncio.Semaphore(5)` to cap concurrent route API calls at 5.

**Rationale**: With 20–50 pre-filtered candidates × 2 transport modes = 40–100 Google Maps calls. At 50 ms average latency each with 5× concurrency ≈ 0.4–1 s. Within the 5 s SC-002 budget with headroom for LLM "why_recommended" generation.

**Graduated fallback**:
1. Not enough candidates → extend `max_minutes_per_leg` by +10 min, retry
2. Still not enough → add "transit" to modes if not already included
3. Still not enough → return best available with `partial: true` + `fallback_reason`

---

## 7. LLM "Why Recommended" Generation

**Decision**: Single batch LLM call per candidate set (6 items). Prompt includes: venue name, category, type tags, gene name, and last-visit history. Use Gemini 2.5 Flash (primary) for speed; expect <1 s for 6 one-sentence reasons in a single structured JSON response.

**Rationale**: One batch call vs. 6 individual calls saves latency and token overhead. Structured output (JSON array of strings) is reliable with Gemini 2.5 Flash.
