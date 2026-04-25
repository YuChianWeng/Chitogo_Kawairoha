# Implementation Plan: ChitoGO PRD State-Machine Trip Wizard

**Branch**: `011-chitogo-prd-wizard` | **Date**: 2026-04-25 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/011-chitogo-prd-wizard/spec.md`

## Summary

Convert ChitoGO from a free-text chat itinerary planner into a state-machine-driven wizard that guides users through a 9-question quiz → accommodation/transport setup → repeating 6-candidate recommendation loop → rated visits → journey summary. The backend adds a new `/api/v1/trip/*` router with 8 endpoints enforcing QUIZ→TRANSPORT→RECOMMENDING→ENDED state transitions; the frontend replaces the chat UI with a multi-page wizard (Vue Router) with QuizPage, SetupPage, TripPage, and SummaryPage.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)  
**Primary Dependencies**: FastAPI 0.111, Pydantic v2, httpx, Gemini 2.5 Flash / Claude Sonnet 4.6, Vue 3 + Vite 5, vue-router 4  
**Storage**: In-memory session store (existing `InMemorySessionStore`) extended with PRD fields; PostgreSQL via Data Service (places + legal lodging); ODS hotel list loaded at Chat Agent startup into memory  
**Testing**: pytest + pytest-asyncio (backend), vitest + @vue/test-utils (frontend)  
**Target Platform**: Linux server (API), mobile browser (Vue 3 SPA, mobile-first)  
**Project Type**: web-service + SPA  
**Performance Goals**: 6-candidate set in <5 s (SC-002); hotel validation <2 s (SC-005); summary load <3 s (SC-007)  
**Constraints**: ≥90% of displayed candidates within reachability constraints; haversine pre-filter × 1.5 safety margin before Google Maps call; state machine rejects out-of-order calls 100%  
**Scale/Scope**: Single-city (Taipei), mobile-first; session TTL managed by existing sweeper

## Constitution Check

Constitution file contains placeholder template — no project-specific gates are ratified. Proceeding without enforced gate checks; standard FastAPI/Pydantic patterns apply.

## Project Structure

### Documentation (this feature)

```text
specs/011-chitogo-prd-wizard/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── trip-api.md
│   └── frontend-state.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/Chat_Agent/app/
├── api/v1/
│   ├── chat.py               (existing — unchanged)
│   ├── health.py             (existing — unchanged)
│   └── trip.py               (NEW — 8 PRD endpoints)
├── orchestration/
│   ├── classifier.py         (existing)
│   └── gene_classifier.py    (NEW — TravelGeneClassifier)
├── services/
│   ├── reachability.py       (NEW — ReachabilityEngine + haversine pre-filter)
│   ├── candidate_picker.py   (NEW — 6-candidate + demand-mode picker)
│   └── go_home_advisor.py    (NEW — GoHomeAdvisor)
└── session/
    └── models.py             (EXTEND — add FlowState enum + PRD session fields)

frontend/src/
├── router/
│   └── index.ts              (NEW — vue-router: /quiz, /setup, /trip, /summary)
├── pages/
│   ├── HomePage.vue          (existing — repurpose as landing / redirect)
│   ├── QuizPage.vue          (NEW)
│   ├── SetupPage.vue         (NEW)
│   ├── TripPage.vue          (NEW — main loop container)
│   └── SummaryPage.vue       (NEW)
├── components/
│   ├── MapPanel.vue          (existing — reused in NavigationPanel)
│   ├── CandidateGrid.vue     (NEW)
│   ├── DemandModal.vue       (NEW)
│   ├── NavigationPanel.vue   (NEW)
│   └── RatingCard.vue        (NEW)
├── services/
│   └── api.ts                (EXTEND — add trip API calls)
└── types/
    ├── itinerary.ts          (existing)
    └── trip.ts               (NEW — PRD type definitions)
```

**Structure Decision**: Web-application (Option 2). Existing backend/Chat_Agent and frontend/ directories are extended in-place. The trip router is a sibling to the existing chat router under the same FastAPI app. The frontend adds vue-router alongside the existing Vue 3 app; the old HomePage becomes a redirect to `/quiz` for new sessions.

## Complexity Tracking

No constitution violations to justify.
