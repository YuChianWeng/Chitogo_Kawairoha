# Feature Specification: Taipei AI Itinerary Planner

**Feature Branch**: `001-taipei-itinerary-planner`
**Created**: 2026-03-29
**Status**: Draft
**Input**: User description: "Build an AI-powered Taipei itinerary planner for the YTP hackathon."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate a Weather-Aware Itinerary (Priority: P1)

A traveler opens the planner, fills in their preferences (district: Da'an, time range: 10:00–14:00, interests: food and cafes, budget: mid-range, companion: solo, preference: indoor-leaning), and submits. Within 10 seconds they receive a 3–5 stop itinerary with suggested arrival times, distances between stops, and a short sentence explaining why each stop was chosen. Because it is a rainy Sunday afternoon, the planner surfaces mostly covered or indoor venues and deprioritizes outdoor parks.

**Why this priority**: This is the core product loop — preference input → contextual recommendation → personalized itinerary. Everything else depends on this working.

**Independent Test**: Can be fully tested end-to-end by submitting a form and verifying an itinerary appears with at least 3 stops, each with a time, a reason, and a venue name.

**Acceptance Scenarios**:

1. **Given** a user submits valid preferences with a rainy forecast, **When** the itinerary is generated, **Then** the itinerary contains 3–5 stops that are predominantly indoor or covered venues.
2. **Given** a user submits preferences for a sunny morning, **When** the itinerary is generated, **Then** the itinerary may include outdoor stops such as parks or street markets.
3. **Given** a user submits the form, **When** the system processes the request, **Then** a complete itinerary is displayed in under 10 seconds.

---

### User Story 2 - Preference Input Form (Priority: P2)

A user visiting the site for the first time sees a clean preference form. They can select or type: district (dropdown of Taipei districts), time range (start time + end time), interests (multi-select tags: food, cafes, art, history, shopping, nature, nightlife, etc.), budget level (budget / mid-range / splurge), companion type (solo / couple / family / friends), and indoor/outdoor preference (indoor / outdoor / no preference). All fields have sensible defaults so the form can be submitted quickly.

**Why this priority**: Without structured preference input the AI has no signal to personalize recommendations. The form is the entry point for the entire experience.

**Independent Test**: Can be fully tested by loading the form, filling it in, and verifying all inputs are captured and submitted correctly — independent of whether the AI backend is live.

**Acceptance Scenarios**:

1. **Given** a user loads the planner, **When** the page renders, **Then** all preference fields are visible with default values pre-filled.
2. **Given** a user selects preferences and submits, **When** the form validates, **Then** no required field blocks submission if defaults are present.
3. **Given** a user selects a time range shorter than 60 minutes, **When** they submit, **Then** a helpful message informs them the time range may not support enough stops.

---

### User Story 3 - Structured Itinerary Output Display (Priority: P2)

After generation, the user sees a structured itinerary card view — not a raw text block or chat reply. Each stop shows: venue name, suggested arrival time, a category tag (e.g., "Café", "Museum"), a 1–2 sentence explanation of why it was recommended, and an approximate travel time from the previous stop.

**Why this priority**: The output format is central to the product's value proposition — making the experience feel like a real itinerary, not a generic chatbot reply.

**Independent Test**: Can be tested by mocking a generated itinerary response and verifying the UI renders all required fields per stop.

**Acceptance Scenarios**:

1. **Given** a generated itinerary, **When** displayed, **Then** each stop card shows: name, time, category tag, reason sentence, and travel time to next stop.
2. **Given** an itinerary with 4 stops, **When** displayed, **Then** stops appear in chronological order with no time conflicts.
3. **Given** a user views the itinerary on a mobile screen, **When** rendered, **Then** stop cards are readable and scrollable without horizontal overflow.

---

### User Story 4 - Weather Context Integration (Priority: P3)

The system automatically fetches current or same-day weather for the selected Taipei district and uses it to adjust the candidate pool. On rainy days, outdoor attractions drop in ranking; indoor spots are surfaced higher. A small weather indicator (icon + temperature) appears at the top of the itinerary output.

**Why this priority**: This is a key differentiator from static lists, but the product can function without it if weather data is unavailable — falling back gracefully.

**Independent Test**: Can be tested by mocking different weather conditions (sunny, rainy) and verifying itinerary composition changes accordingly.

**Acceptance Scenarios**:

1. **Given** the weather service returns rain, **When** the itinerary is generated, **Then** indoor venues appear in at least 75% of the 3–5 stops.
2. **Given** the weather service is unavailable, **When** the itinerary is generated, **Then** the system falls back gracefully and still produces a valid itinerary without exposing an error to the user.
3. **Given** the itinerary is displayed and weather data is available, **When** rendered, **Then** a weather summary (icon, condition, temperature) is visible at the top of the output.

---

### User Story 5 - Ranked Candidate Places (Priority: P3)

Before final itinerary assembly, the system maintains an internal ranked list of candidate venues based on preference match, weather suitability, and recency signals (trending or recently popular). The ranking shapes which stops are selected and in what order.

**Why this priority**: The ranking layer determines output quality. It can be simplified for MVP but must exist to prevent random or geographically scattered results.

**Independent Test**: Can be tested by inspecting the intermediate ranked list (via debug mode or returned metadata) and verifying that high-scoring candidates under given preferences appear in the final itinerary.

**Acceptance Scenarios**:

1. **Given** a preference for "food" in Da'an district, **When** candidates are ranked, **Then** food venues in or near Da'an appear in the top positions.
2. **Given** two venues with equal preference match but one is trending, **When** ranked, **Then** the trending venue scores higher.
3. **Given** rain conditions, **When** candidates are ranked, **Then** outdoor-only venues rank below indoor venues of equivalent interest match.

---

### Edge Cases

- What happens when the selected district has fewer than 3 matching venues for the given preferences?
- How does the system handle a time range under 60 minutes that cannot accommodate 3 stops?
- What if the user selects interests with no matching venues (e.g., "surfing" in a landlocked district)?
- What if weather data returns an unexpected format or times out?
- What if the AI service is slow — does the UI show a loading state and gracefully handle a timeout?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present a preference input form with fields for district, time range (start + end), interests (multi-select), budget level, companion type, and indoor/outdoor preference.
- **FR-002**: System MUST provide sensible default values for all form fields so the form can be submitted without manual input.
- **FR-003**: System MUST fetch same-day weather data for the user's selected Taipei district before generating the itinerary.
- **FR-004**: System MUST generate an itinerary of 3 to 5 stops based on the submitted preferences and current weather context.
- **FR-005**: Each stop in the itinerary MUST include: venue name, suggested arrival time, category tag, a 1–2 sentence personalized explanation, and estimated travel time from the prior stop.
- **FR-006**: System MUST rank candidate venues by preference match score, weather suitability, and recency/trend signals before selecting final stops.
- **FR-007**: System MUST display the itinerary as structured cards, not as a conversational chat reply or unformatted text block.
- **FR-008**: System MUST complete itinerary generation and display the result within 10 seconds of form submission under normal operating conditions.
- **FR-009**: System MUST adjust itinerary composition based on weather — rainy conditions MUST reduce the proportion of outdoor stops in the output.
- **FR-010**: System MUST handle weather data unavailability gracefully, falling back to preference-only recommendations without displaying an error to the user.
- **FR-011**: System MUST display a weather summary (condition + temperature) at the top of the itinerary output when weather data is available.
- **FR-012**: System MUST warn the user if the selected time range is too short to support 3 stops (fewer than 60 minutes).
- **FR-013**: System MUST sequence stops to minimize geographic travel friction by ordering them in a logical route (clustered by proximity or area).

### Key Entities

- **UserPreferences**: A set of inputs submitted per session — district, time range, interest tags, budget level, companion type, indoor/outdoor preference.
- **Venue**: A candidate place in Taipei — name, district, category, indoor/outdoor flag, average cost level, geo-coordinates, trend score.
- **WeatherContext**: Same-day weather snapshot for the selected district — condition (sunny/cloudy/rainy/etc.), temperature, precipitation probability.
- **ItineraryStop**: A selected venue with computed fields — arrival time, travel time from previous stop, personalized explanation, ranking score.
- **Itinerary**: An ordered collection of 3–5 ItineraryStops generated for a single user session, anchored to a time range and weather context.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can generate a complete, coherent 3–5 stop Taipei itinerary within 10 seconds of submitting preferences.
- **SC-002**: When rainy weather is detected, at least 75% of recommended stops are indoor or covered venues — a noticeably different composition from a sunny-day itinerary for the same preferences.
- **SC-003**: The itinerary output is displayed as a structured card-based layout; zero stops may be rendered as raw unformatted text.
- **SC-004**: 90% of generated itineraries contain stops that are geographically clustered or sequenced to minimize backtracking (all stops within 2 km of each other, or ordered by proximity).
- **SC-005**: Users can complete the preference form and submit in under 2 minutes without any instructions.
- **SC-006**: The system handles weather service unavailability and still returns a valid itinerary in 100% of fallback scenarios.

## Assumptions

- The MVP targets users exploring Taipei on the same day; future-date itinerary planning is out of scope for v1.
- A curated set of Taipei venues covering major districts and interest categories is available as seed data; real-time venue discovery from external sources is a stretch goal.
- Trend/recency signals are approximated for MVP (e.g., manually tagged "trending" flag on venues) rather than pulled from live social APIs.
- The planner is a single-session tool — no user accounts, saved itineraries, or login required for MVP.
- Mobile-responsive display is required; native app packaging is out of scope.
- The system targets tourists and day-visitors to Taipei; local commuter use cases are not prioritized.
- Weather data is sourced from a publicly available weather service for Taipei; API key management is the deployer's responsibility.
- English is the primary display language for MVP; Traditional Chinese support is a future enhancement.
