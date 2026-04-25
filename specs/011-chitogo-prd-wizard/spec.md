# Feature Specification: ChitoGO PRD State-Machine Trip Wizard

**Feature Branch**: `011-chitogo-prd-wizard`  
**Created**: 2026-04-25  
**Status**: Draft  
**Input**: User description: "base on message.txt help us implement ChitoGO PRD wizard trip planning system"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preference Quiz & Travel Gene Onboarding (Priority: P1)

A first-time user launches ChitoGO and is guided through a 9-question preference quiz. Based on their answers the system assigns a "travel gene" category and a corresponding mascot character that will represent their trip style throughout the session.

**Why this priority**: This is the entry point of every session. Without it no personalization is possible and no further trip planning can proceed.

**Independent Test**: A user can open the app, complete all 9 quiz questions, and see a travel gene result card with mascot image and gene description — delivering a complete onboarding experience even before any venue recommendations are made.

**Acceptance Scenarios**:

1. **Given** a new session, **When** the user opens the app, **Then** the 9-question quiz is presented as a card-style flow with a progress indicator showing current question number out of 9.
2. **Given** Q1, **When** the user sees the first question, **Then** three answer options are available (A/B/C); for Q2–Q9 two options (A/B) are available.
3. **Given** all 9 answers submitted, **When** the system classifies answers, **Then** the user is shown a travel gene card (one of: 文清, 親子, 不常來, 夜貓子, 一日, 野外) with a mascot illustration and a short gene description.
4. **Given** two genes score within 1 point of each other, **When** a tiebreaker is needed, **Then** the system resolves the tie and still produces exactly one travel gene result.

---

### User Story 2 - Trip Setup: Accommodation, Return Time & Transport (Priority: P1)

After receiving their travel gene, the user configures the session by providing accommodation details, an optional return time, and their preferred transport modes with a maximum travel time per leg.

**Why this priority**: Transport and time constraints drive every subsequent recommendation. Without setup the reachability filter has no parameters and candidates cannot be scoped.

**Independent Test**: A user can complete the setup form, submit it successfully, and the system stores all configuration so that subsequent candidate requests respect the entered constraints.

**Acceptance Scenarios**:

1. **Given** the setup page, **When** the user selects "已訂住宿" (accommodation booked) and enters a hotel name, **Then** the system validates the name against the legal accommodation registry and displays a green check badge if valid or a warning with alternative suggestions if invalid.
2. **Given** the user selects "尚未訂住宿" (not yet booked), **When** they pick a district and budget range, **Then** the system records the preference without requiring a specific hotel name.
3. **Given** the user provides a return time and destination (hotel / station), **When** setup is submitted, **Then** the session stores return time for later "該回家了" calculations.
4. **Given** the transport configuration section, **When** the user selects one or more transport modes and sets a maximum minutes-per-leg slider, **Then** all subsequent candidate sets are filtered to venues reachable within those constraints.

---

### User Story 3 - Six-Candidate Recommendation Loop (Priority: P1)

The core trip experience: the user repeatedly sees 6 venue candidates (3 restaurants + 3 attractions), picks one, navigates there, and rates it. The loop continues until they decide to go home.

**Why this priority**: This is the primary value loop of the entire product. Every other feature either feeds into it or extends it.

**Independent Test**: Starting from a configured session, a user can receive 6 candidates, select one, navigate to it, rate it, and be returned to a fresh set of 6 candidates — the full loop cycle works end-to-end.

**Acceptance Scenarios**:

1. **Given** a configured session, **When** the candidate screen loads, **Then** exactly 6 cards are shown: 3 restaurants and 3 attractions, each filtered to the user's reachable set.
2. **Given** a candidate card, **When** the user views it, **Then** they see: venue name, category badge (restaurant/attraction), distance estimate in minutes, star rating, and a one-sentence "why recommended" explanation.
3. **Given** fewer than 3 restaurants available within reach, **When** the system builds the candidate set, **Then** it fills the remaining slots from attractions and marks the response with a partial flag.
4. **Given** the user selects a candidate, **When** the selection is submitted, **Then** the system returns navigation data (address, coordinates, estimated travel time) and moves the session to NAVIGATING state.
5. **Given** a 5-star rating submitted after a visit, **When** the next candidate set is requested, **Then** the candidates reflect boosted affinity for the category and type of the 5-star venue.
6. **Given** a 1–2 star rating, **When** the next candidate set is requested, **Then** the candidates penalize that category and type in scoring.

---

### User Story 4 - Alternative Demand Mode (Priority: P2)

If no candidate in the 6-card set appeals to the user, they can tap "None of these" and enter a free-text or guided demand to receive 3 alternative candidates.

**Why this priority**: Escape valve for when the algorithm doesn't match user mood. Prevents friction and dead-ends without requiring a full session restart.

**Independent Test**: Tapping "None of these" opens a demand modal; entering a description and submitting replaces the grid with 3 alternative venue cards.

**Acceptance Scenarios**:

1. **Given** the 6-candidate grid, **When** the user taps "None of these," **Then** a demand modal opens with a free-text input and placeholder examples (e.g., "我想找有點文藝的地方").
2. **Given** a submitted demand text, **When** the demand is processed, **Then** the grid is replaced with 3 alternative venue cards that match the stated demand.
3. **Given** insufficient alternatives exist within reach, **When** demand is processed, **Then** the system returns the best available matches with an explanatory note.

---

### User Story 5 - Navigation to Selected Venue (Priority: P2)

After selecting a venue, the user sees a navigation screen with destination details, deep-link buttons to mapping apps, and an LLM-generated encouragement message.

**Why this priority**: Bridges the digital recommendation to physical navigation — without it users cannot act on their selection.

**Independent Test**: After selecting a venue, the user can tap a map deep-link and be taken to the correct destination in their preferred maps app.

**Acceptance Scenarios**:

1. **Given** a selected venue, **When** the navigation screen appears, **Then** it shows: venue name, address, map thumbnail centered on destination, and estimated travel time.
2. **Given** the navigation screen, **When** the user taps "開啟地圖," **Then** they are offered a Google Maps deep-link and an Apple Maps fallback link, each pre-filled with the correct coordinates and transport mode.
3. **Given** the navigation screen, **When** the LLM message loads, **Then** a short encouraging message is displayed below the navigation buttons.
4. **Given** the user taps "我到了！," **Then** the session transitions to the RATING state and the rating screen appears.

---

### User Story 6 - Post-Visit Rating (Priority: P2)

After arriving at a venue, the user rates their experience with a 1–5 star input and optional quick-tag metadata. The rating feeds back into future recommendations.

**Why this priority**: Closes the feedback loop that differentiates ChitoGO from a static guide — personalization improves every stop.

**Independent Test**: After tapping "我到了！," a rating card appears; submitting a rating returns the user to the 6-candidate grid with recommendations updated for the rated category.

**Acceptance Scenarios**:

1. **Given** the rating screen, **When** it loads, **Then** the visited venue name, photo, and an animated 5-star tap input are displayed.
2. **Given** the rating screen, **When** the user taps optional quick-tag buttons (e.g., "食物很好吃," "人太多了"), **Then** the tags are submitted alongside the numeric rating as metadata.
3. **Given** a submitted rating, **When** the rating is recorded, **Then** the session logs the visit with timestamp, star count, and tags, and adjusts gene affinity weights accordingly.

---

### User Story 7 - Exit & Full Journey Summary (Priority: P3)

At any point the user can tap the always-visible "我想回家" button to end the trip and view a full journey summary timeline.

**Why this priority**: Provides closure and a shareable memory artifact. Lower priority as the trip loop works without it, but essential for a complete product.

**Independent Test**: Tapping "我想回家" at any state produces a summary page listing every visited stop with time, name, rating, total distance, and a mascot farewell message.

**Acceptance Scenarios**:

1. **Given** any trip state, **When** the user taps "我想回家," **Then** the session transitions to ENDED and the summary page is displayed.
2. **Given** the summary page, **When** it loads, **Then** it shows a chronological timeline with: stop number, venue name, arrival time, and star rating for each visited stop, plus total elapsed time and total distance covered.
3. **Given** the summary page, **When** the page renders, **Then** an LLM-generated mascot farewell message is displayed.
4. **Given** the summary page, **When** the user taps the share button, **Then** the summary is copied to clipboard or triggers the native share dialog.

---

### User Story 8 - "該回家了" Time-Based System Reminder (Priority: P3)

When the calculated return time approaches (accounting for transit back to accommodation/station), the system shows a non-blocking banner reminding the user it's time to head home.

**Why this priority**: Safety net for users who lose track of time. Important for trust but does not block the core loop.

**Independent Test**: With a return time set, the system fires a reminder banner at the correct calculated time, which the user can dismiss or confirm to end the trip.

**Acceptance Scenarios**:

1. **Given** a session with a return time set, **When** the current time equals or exceeds (return time − transit time − 30 minutes), **Then** a non-blocking banner appears with the reminder message and two options: "繼續玩" or "回家去."
2. **Given** the reminder was already shown, **When** the user dismisses it, **Then** the system does not re-show the reminder for at least 10 minutes.
3. **Given** no return time is set, **When** the should-go-home check is polled, **Then** the system returns a "no reminder" response and no banner is shown.
4. **Given** the user taps "回家去," **Then** the session ends and the journey summary page is displayed.

---

### Edge Cases

- What happens when no venues are reachable within the configured transport constraints? System applies graduated fallbacks: extend time limit by +10 minutes, then broaden transport mode, then emit a fallback reason message to the user.
- How does the system handle the cold-start first stop with no ratings yet? Pure gene affinity + time-of-day signal (morning → café/breakfast emphasis; evening → bars/night markets emphasis).
- What if the user's hotel name contains typos or minor spelling variations? Fuzzy matching returns the closest valid match with a confidence indicator.
- What if the trip runs long enough that the return time has already passed when the user loads candidates? System immediately shows the "該回家了" reminder banner on the next candidates load.
- What if the user loses network connectivity mid-trip? Navigation deep-links remain functional (opened in external maps app); returning to the app restores session state from local storage.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present a 9-question preference quiz as the first step of every new session
- **FR-002**: System MUST classify user quiz answers into exactly one of 6 travel gene categories (文清, 親子, 不常來, 夜貓子, 一日, 野外)
- **FR-003**: System MUST assign a mascot character to each travel gene and display it persistently throughout the session
- **FR-004**: Users MUST be able to declare accommodation as either booked (with hotel name) or not yet booked (with district and budget preference)
- **FR-005**: System MUST validate a provided hotel name against the official legal accommodation registry and return validation status plus alternative suggestions when invalid
- **FR-006**: Users MUST be able to set an optional return time and return destination (accommodation or transit station)
- **FR-007**: Users MUST be able to select one or more transport modes and a maximum travel-time budget per leg
- **FR-008**: System MUST enforce a session state machine with states: QUIZ → TRANSPORT → RECOMMENDING → ENDED; API calls that violate state order MUST be rejected with a clear error
- **FR-009**: System MUST present exactly 6 venue candidates per recommendation round: 3 restaurants and 3 attractions, unless a partial fill is unavoidable (flagged in response)
- **FR-010**: All candidates MUST be filtered to only venues reachable within the user's configured transport mode(s) and time budget, with graduated fallback when the reachable set is too small
- **FR-011**: Each candidate MUST include: name, category (restaurant/attraction), distance estimate in travel minutes, rating score, address, coordinates, and a one-sentence personalized recommendation reason
- **FR-012**: System MUST adjust candidate scoring using gene affinity weights; 5-star ratings MUST boost (+0.2) and 1–2 star ratings MUST penalize (−0.3, capped) the relevant category/type weights for the session
- **FR-013**: Users MUST have an always-visible "我想回家" control accessible from every trip state without scrolling
- **FR-014**: System MUST support a demand mode: user submits free-text describing desired alternatives and receives 3 alternative venue candidates in response
- **FR-015**: After venue selection, system MUST provide navigation deep-links for Google Maps and Apple Maps pre-filled with destination coordinates and transport mode
- **FR-016**: System MUST transition the session to a RATING state after the user confirms arrival ("我到了！") and prompt for a 1–5 star rating
- **FR-017**: After submitting a rating, system MUST record the visit (venue, timestamp, stars, optional tags) and update gene affinity weights before the next recommendation round
- **FR-018**: System MUST calculate a "should go home" trigger time as: return_time − transit_minutes_to_destination − 30 minutes; when triggered, display a non-blocking reminder banner
- **FR-019**: System MUST suppress "該回家了" re-notifications within a 10-minute cooldown window per session
- **FR-020**: On trip exit, system MUST produce a journey summary including: chronological stop list with arrival times and ratings, total elapsed time, approximate total distance, and a mascot farewell message

### Key Entities

- **Session**: Unique identifier, travel gene, mascot, accommodation details, return time, return destination, transport configuration, visited stops list, current flow state (QUIZ/TRANSPORT/RECOMMENDING/ENDED), gene affinity weights map, go-home reminder last-fired timestamp
- **TravelGene**: Gene type name (one of 6), associated mascot identifier, gene description text, base affinity weight map across venue categories
- **Venue/Candidate**: Venue identifier, name, category (restaurant or attraction), location coordinates, address, base rating, district, type tags, photo reference
- **CandidateCard**: Venue reference, computed travel time in minutes, personalized recommendation reason (one sentence), partial-fill flag
- **VisitedStop**: Venue reference, arrival timestamp, star rating (1–5), optional quick-tag list
- **Hotel**: Official name, district, price tier range, legal registration status, last-updated date
- **JourneySummary**: Ordered list of VisitedStops, total trip duration, approximate total distance, mascot farewell message text

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete the 9-question quiz and view their travel gene result in under 3 minutes from first opening the app
- **SC-002**: Each 6-candidate recommendation set is delivered within 5 seconds of the user reaching the candidate screen
- **SC-003**: At least 90% of displayed candidates are within the user's configured reachability constraints (transport mode + time budget)
- **SC-004**: The full onboarding-to-first-venue-selection flow (quiz + setup + first candidate pick) completes in under 5 minutes for a typical user
- **SC-005**: Hotel name validation returns a result (valid, invalid + alternatives, or fuzzy match) within 2 seconds of input submission
- **SC-006**: "該回家了" reminder banner appears within 2 minutes of the calculated trigger time
- **SC-007**: Journey summary loads within 3 seconds of the user initiating the exit action
- **SC-008**: Rating-adjusted candidate sets are served on the very next recommendation round (within 1 cycle after rating submission)
- **SC-009**: The state machine rejects out-of-order API calls 100% of the time with a descriptive error message
- **SC-010**: The "我想回家" control is visible and interactable in every UI state without scrolling

## Assumptions

- Users have a stable mobile internet connection throughout their trip; offline fallback is limited to previously-opened navigation deep-links
- The legal accommodation ODS file (`旅宿列表匯出_20260425103741.ods`) in the repo is the authoritative source for hotel validation; a "last updated" disclaimer is shown in validation responses
- Q1 uses A/B/C (three options) and Q2–Q9 use A/B (two options) as the default quiz format; this can be revised without changing the API contract
- Hotel alternative suggestions default to same-district, similar-price-tier filtering; cross-district alternatives are out of scope for v1
- The reachability filter uses haversine distance as a pre-filter (safety margin 1.5×) before calling the routing API to reduce external API load
- Cold-start recommendation (first stop, no ratings yet) uses time-of-day signal combined with pure gene affinity weighting
- "該回家了" polling occurs every 60 seconds from the frontend; server-push notifications are out of scope for v1
- Session state is persisted server-side; session_id and travel gene are also stored in browser localStorage for reconnection after network interruptions
- The 6 travel gene scoring rules use a deterministic heuristic matrix initially; the scoring engine can be swapped without changing the API surface
- Mobile-first UI is the primary target; desktop layout optimization is a stretch goal for v1
