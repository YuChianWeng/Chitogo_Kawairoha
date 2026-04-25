# Frontend State Contract

**Framework**: Vue 3 + TypeScript + vue-router 4  
**State management**: Vue `reactive()` / `ref()` (no Pinia for v1 — session is short-lived)  
**Persistence**: `localStorage` for session ID and gene (reconnect after network interruption)

---

## Routes

| Route | Component | Guard |
|-------|-----------|-------|
| `/` | redirect → `/quiz` | none |
| `/quiz` | `QuizPage.vue` | none (always accessible) |
| `/setup` | `SetupPage.vue` | requires `chitogo_session_id` in localStorage |
| `/trip` | `TripPage.vue` | requires `chitogo_session_id` AND `chitogo_gene` |
| `/summary` | `SummaryPage.vue` | requires `chitogo_session_id` |

If guard fails, redirect to `/quiz`.

---

## localStorage Keys

| Key | Value | Set when |
|-----|-------|----------|
| `chitogo_session_id` | string | Session created (quiz page load) |
| `chitogo_gene` | string | POST /trip/quiz succeeds |
| `chitogo_mascot` | string | POST /trip/quiz succeeds |

---

## Trip Page Sub-States (local to TripPage.vue)

TripPage manages an internal `tripPhase` reactive ref that mirrors the backend session state:

```typescript
type TripPhase = 'SELECTING' | 'NAVIGATING' | 'RATING' | 'ENDED'
```

| Phase | Component visible | Next trigger |
|-------|------------------|--------------|
| `SELECTING` | `CandidateGrid.vue` | User taps a candidate card |
| `NAVIGATING` | `NavigationPanel.vue` | User taps "我到了！" |
| `RATING` | `RatingCard.vue` | User submits rating |
| `ENDED` | redirect to `/summary` | — |

---

## API Service Contract (frontend/src/services/api.ts additions)

All trip methods added to the existing `api.ts` axios client:

```typescript
// Session creation (existing endpoint reused)
createSession(): Promise<{ session_id: string }>

// New trip methods
submitQuiz(sessionId: string, answers: QuizAnswers): Promise<QuizResult>
submitSetup(sessionId: string, setup: TripSetup): Promise<SetupResult>
getCandidates(sessionId: string, lat: number, lng: number): Promise<CandidatesResult>
selectVenue(sessionId: string, venueId: string | number, lat: number, lng: number): Promise<SelectResult>
submitRating(sessionId: string, stars: number, tags: string[]): Promise<RateResult>
submitDemand(sessionId: string, text: string, lat: number, lng: number): Promise<DemandResult>
checkGoHome(sessionId: string, lat: number, lng: number): Promise<GoHomeStatus>
getSummary(sessionId: string): Promise<JourneySummary>
```

---

## TypeScript Types (frontend/src/types/trip.ts)

```typescript
export type TravelGene = '文清' | '親子' | '不常來' | '夜貓子' | '一日' | '野外'
export type TransportMode = 'walk' | 'transit' | 'drive'
export type FlowState = 'QUIZ' | 'TRANSPORT' | 'RECOMMENDING' | 'RATING' | 'ENDED'

export interface QuizAnswers {
  Q1: 'A' | 'B' | 'C'
  Q2: 'A' | 'B'
  Q3: 'A' | 'B'
  Q4: 'A' | 'B'
  Q5: 'A' | 'B'
  Q6: 'A' | 'B'
  Q7: 'A' | 'B'
  Q8: 'A' | 'B'
  Q9: 'A' | 'B'
}

export interface QuizResult {
  session_id: string
  travel_gene: TravelGene
  mascot: string
  gene_description: string
}

export interface AccommodationInput {
  booked: boolean
  hotel_name?: string
  district?: string
  budget_tier?: 'budget' | 'mid' | 'luxury'
}

export interface TripSetup {
  accommodation: AccommodationInput
  return_time?: string  // HH:MM
  return_destination?: string
  transport: {
    modes: TransportMode[]
    max_minutes_per_leg: number
  }
}

export interface SetupResult {
  session_id: string
  accommodation_status: 'validated' | 'fuzzy_match' | 'not_found' | 'not_required'
  hotel_validation: HotelValidation | null
  setup_complete: boolean
}

export interface HotelValidation {
  valid: boolean
  matched_name: string | null
  match_type: 'exact' | 'fuzzy' | null
  confidence: number | null
  district: string | null
  address: string | null
  alternatives: Array<{ name: string; district: string | null; address: string | null; confidence: number }>
  last_updated: string
}

export interface CandidateCard {
  venue_id: string | number
  name: string
  category: 'restaurant' | 'attraction'
  primary_type: string | null
  address: string | null
  lat: number
  lng: number
  rating: number | null
  distance_min: number
  why_recommended: string
}

export interface CandidatesResult {
  session_id: string
  candidates: CandidateCard[]
  partial: boolean
  fallback_reason: string | null
  restaurant_count: number
  attraction_count: number
}

export interface SelectResult {
  session_id: string
  venue: Pick<CandidateCard, 'venue_id' | 'name' | 'category' | 'address' | 'lat' | 'lng'>
  navigation: {
    google_maps_url: string
    apple_maps_url: string
    estimated_travel_min: number
  }
  encouragement_message: string
}

export interface RateResult {
  session_id: string
  visit_recorded: boolean
  stop_number: number
  affinity_update: { category: string; adjustment: number }
}

export interface DemandResult {
  session_id: string
  alternatives: CandidateCard[]
  fallback_reason: string | null
}

export interface GoHomeStatus {
  session_id: string
  remind: boolean
  message: string | null
  time_remaining_min: number | null
}

export interface VisitedStopSummary {
  stop_number: number
  venue_id: string | number
  venue_name: string
  category: 'restaurant' | 'attraction'
  address: string | null
  arrived_at: string  // ISO datetime string
  star_rating: number
  tags: string[]
}

export interface JourneySummary {
  session_id: string
  travel_gene: TravelGene
  mascot: string
  stops: VisitedStopSummary[]
  total_stops: number
  total_elapsed_min: number
  total_distance_m: number
  mascot_farewell: string
}
```

---

## Geolocation Usage

TripPage requests `navigator.geolocation.getCurrentPosition()` on mount and polls every 30 seconds during `SELECTING` and `NAVIGATING` phases. Coordinates are passed to `getCandidates`, `selectVenue`, `checkGoHome`, and `submitDemand`.

If geolocation is denied, TripPage shows a banner prompting the user to enter their current location manually (district picker fallback).

---

## "我想回家" Button

Rendered as a fixed-position button at the bottom of TripPage.vue, visible in all `tripPhase` values except `ENDED`. Tap triggers a confirmation modal, then calls `getSummary()` which transitions the session to ENDED and navigates to `/summary`.

---

## "該回家了" Banner

A non-blocking `<div>` overlay at the top of TripPage.vue. Shown when `checkGoHome()` returns `remind: true`. Contains two buttons:
- **繼續玩** — dismisses banner; client sets a 10-min local suppress timer
- **回家去** — calls `getSummary()` and navigates to `/summary`
