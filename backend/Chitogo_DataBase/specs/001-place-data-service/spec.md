# Feature Specification: Place Data Service

**Feature Branch**: `001-place-data-service`
**Created**: 2026-04-16
**Status**: Clarified
**Input**: User description: "Build a standalone backend data service for the Chito-Go project focused on data ingestion, normalization, storage, and retrieval for place data."

## Clarifications

### Session 2026-04-16

- Q: Is this a standalone data service only, with no bundled product logic? → A: Yes. This is a standalone data service only. No other service logic is bundled here.
- Q: Will another backend consume this service? → A: Yes. Another backend will later consume this service via its REST endpoints.
- Q: What is excluded from this service's ownership? → A: The service owns no chat logic, itinerary orchestration, authentication, or frontend concerns.
- Q: Must the internal place schema be independent of Google's API response shape? → A: Yes. The internal schema must not depend on Google's response shape; it must remain source-agnostic so other data sources can be added later without schema changes.
- Q: What should retrieval endpoints return — normalized internal objects or raw Google payloads? → A: Retrieval endpoints must return normalized internal place objects only, never raw Google Places response objects.
- Q: Is startup-based table creation acceptable for now? → A: Yes, for local development. The schema must remain migration-friendly so tooling can be added later.
- Q: What is the scope of the current milestone? → A: Local development correctness. Not full production deployment readiness.
- Q: How should ingestion handle repeated submissions for the same place? → A: Ingestion MUST upsert records by google_place_id (insert on first occurrence, update on subsequent).
- Q: Is raw payload retention required? → A: Yes. The original raw Google Places payload must be stored in place_source_google for debugging and future remapping.
- Q: Is place_features in scope even if scores are not fully computed? → A: Yes. place_features is in scope for this milestone. Some score values may be null or placeholder initially.
- Q: How complex should retrieval filtering be? → A: Simple filtering only — by district, primary type, indoor status, budget level, and minimum rating. Single-record detail lookup by internal ID. Complex querying is deferred.
- Q: Is a crawler or social review pipeline in scope? → A: No. No crawler or social review pipeline is in scope for this milestone.
- Q: How should missing nested fields in ingestion payloads be handled? → A: Gracefully. Missing nested fields must not cause ingestion failure; the place record is created or updated with whatever data is available.
- Q: What must seed scripts verify? → A: Seed scripts must avoid creating duplicate records and must exercise both storage paths: the normalized places table and the raw source place_source_google table.
- Q: What is the governing principle for deciding whether a field belongs in places vs place_features? → A: `places` holds all normalized fields directly needed for displaying or filtering a place, including derived fields such as `indoor`, `outdoor`, `budget_level`, `trend_score`, and `confidence_score`. `place_features` holds extended audience and context ranking scores (e.g., couple_score, family_score, food_score) that are consumed only by downstream recommendation and ranking systems and are not used for direct filtering or display.
- Q: Should ingestion be exposed as an HTTP endpoint, triggered internally only, or both? → A: Both. The service exposes ingestion as an HTTP POST endpoint for runtime use by any authorized caller, AND provides a standalone script for CLI and local development use. Both paths share the same underlying ingestion logic.
- Q: Which fields are required for a valid ingested place record? → A: `google_place_id` and `display_name` are both required for a normalized place record to be created in the places table. All other fields are optional. The raw source payload MUST still be retained in place_source_google even if `display_name` is absent — payload retention is unconditional once `google_place_id` is present.
- Q: When are place_features records created — auto on ingest, explicit write only, or optionally on ingest? → A: Optional on ingest. The ingestion payload MAY include a features block; if present, the corresponding place_features row is created or updated. If absent, the place_features row is left untouched. No automatic creation occurs. This allows scores to be submitted at ingestion time or deferred to a later independent write.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Query Normalized Place Data (Priority: P1)

A downstream backend service needs to retrieve normalized place records to power itinerary generation, recommendations, or user-facing workflows. It must be able to list places with filters and fetch the full detail of any individual place by its identifier.

**Why this priority**: This is the primary output of the service. Without queryable, normalized place data, the entire downstream product has nothing to work with. All other stories depend on data being available here first.

**Independent Test**: Can be tested by pre-seeding a small set of place records and verifying that the list endpoint returns the correct filtered results and the detail endpoint returns the correct full record.

**Acceptance Scenarios**:

1. **Given** place records exist, **When** a downstream service requests a list of places filtered by district, **Then** only places in that district are returned in the response.
2. **Given** place records exist, **When** a downstream service requests a list of places filtered by type, indoor status, or budget level, **Then** only matching places are returned.
3. **Given** place records exist and a minimum rating filter is applied, **When** the request is made, **Then** only places meeting or exceeding the rating threshold are included.
4. **Given** a valid place identifier, **When** a downstream service requests the place detail, **Then** all normalized fields for that place are returned.
5. **Given** an invalid or unknown place identifier, **When** the detail is requested, **Then** the service returns a clear not-found response.

---

### User Story 2 - Ingest Google Places Data (Priority: P2)

An operator or automated pipeline needs to submit raw Google Places payloads to the service so that the data is normalized into the internal place schema, stored, and becomes queryable.

**Why this priority**: Without ingestion, there is no data to retrieve. This is the entry point for populating the service. It is ranked P2 because the retrieval structure must be defined first for ingestion to target it correctly.

**Independent Test**: Can be tested by submitting a sample Google Places JSON payload and confirming that a normalized place record is created and the raw payload is stored for later inspection.

**Acceptance Scenarios**:

1. **Given** a raw Google Places JSON payload with a `google_place_id`, **When** it is submitted to the ingestion endpoint, **Then** a normalized place record is created or updated by `google_place_id`.
2. **Given** a payload is re-submitted for an existing `google_place_id`, **When** ingestion runs, **Then** the existing record is updated rather than duplicated.
3. **Given** a payload with missing optional nested fields, **When** ingestion runs, **Then** missing fields are handled gracefully and the record is still created with available data.
4. **Given** a payload without `google_place_id`, **When** ingestion is attempted, **Then** the service rejects it with a clear error response.
5. **Given** a valid payload is ingested, **When** the raw payload is stored, **Then** it is preserved in full and associated with the resulting place record for future inspection or reprocessing.

---

### User Story 3 - Monitor Service Health (Priority: P3)

A developer or infrastructure operator needs to verify that the data service is up and its backing store is reachable, so they can confirm deployment success and catch connectivity failures early.

**Why this priority**: This is the simplest story but essential for operational confidence. It enables monitoring and readiness checks without requiring a full data query.

**Independent Test**: Can be tested immediately after service startup by calling the health endpoint and verifying a healthy status response with database connectivity confirmed.

**Acceptance Scenarios**:

1. **Given** the service is running and the database is reachable, **When** the health endpoint is called, **Then** the response indicates a healthy status.
2. **Given** the database is unreachable, **When** the health endpoint is called, **Then** the response clearly indicates an unhealthy state rather than silently failing.

---

### User Story 4 - Seed Place Data for Development and Testing (Priority: P4)

A developer needs to populate the service with a representative set of place records so they can test downstream integrations, verify retrieval behavior, and validate the full data flow without waiting for live Google Places data.

**Why this priority**: Speeds up development by allowing immediate testing of retrieval and ingestion behavior. Not required for production but critical for development velocity.

**Independent Test**: Can be tested by running the seed script and confirming that a set of place records, source payloads, and feature records are present and queryable.

**Acceptance Scenarios**:

1. **Given** the database is empty, **When** the seed script is run, **Then** a defined set of sample place records is created with normalized data, raw source payloads, and derived feature scores.
2. **Given** the seed script has already been run, **When** it is run again, **Then** it does not create duplicate records.

---

### Edge Cases

- What happens when the ingestion payload contains unexpected or unknown fields? (Graceful ignore — only known fields are mapped; extras are discarded.)
- What happens when a payload has `google_place_id` but no `display_name`? (Raw payload is stored in place_source_google; no places record is created. No error is raised — the partial ingest is silent but auditable via the stored raw payload.)
- What happens when a payload has neither `google_place_id` nor `display_name`? (Entire payload is rejected with a clear error response; nothing is stored.)
- What happens when a filter combination returns zero results? (Empty list returned, not an error.)
- What happens when the database connection is lost mid-request? (Request fails cleanly with a service error response, not a crash.)
- What happens when a place's raw source payload is very large? (Stored as-is without truncation.)
- What happens when derived feature scores are not yet computed for a place? (Place is still returned; place_features fields are absent or null.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The service MUST expose an endpoint that returns a list of normalized internal place records, supporting filters for district, primary type, indoor/outdoor status, budget level, and minimum rating. Responses MUST use the internal normalized schema, not raw source payloads.
- **FR-002**: The service MUST expose an endpoint that returns the full normalized internal detail for a single place by its internal identifier. The response MUST use the internal normalized schema.
- **FR-003**: The service MUST expose an HTTP POST endpoint that accepts a raw Google Places JSON payload and ingests it into the internal place schema, upserting by `google_place_id`. The service MUST also provide a standalone CLI/script entry point that invokes the same ingestion logic, usable for local development and batch seeding without making HTTP calls.
- **FR-004**: The service MUST store the original raw Google Places payload associated with each ingested place, preserving it for later debugging, remapping, or reprocessing.
- **FR-005**: The service MUST store derived feature scores associated with a place in a separate place_features record. The ingestion payload MAY include an optional features block; if present, the place_features row is created or updated. If the features block is absent, the place_features row is left untouched — no automatic creation occurs. This allows scores to be submitted at ingestion time or deferred to a later independent write.
- **FR-006**: The ingestion pipeline MUST handle missing or null nested fields in the source payload gracefully, continuing to create or update the place record with available data.
- **FR-007**: For a normalized place record to be created in the places table, the ingestion payload MUST contain both `google_place_id` and `display_name`; payloads missing either field MUST NOT produce a places record. The raw source payload MUST still be stored in place_source_google as long as `google_place_id` is present, regardless of whether `display_name` is available. Payloads with no `google_place_id` MUST be rejected entirely.
- **FR-008**: The service MUST expose a health check endpoint that confirms both service availability and database connectivity.
- **FR-009**: The service MUST support a seed or test script that populates the database with a representative set of place records for development use. The script MUST verify both the normalized places table and the raw source place_source_google table are populated, and MUST be idempotent (safe to run multiple times without creating duplicates).
- **FR-010**: The service MUST NOT implement chat workflows, authentication, itinerary generation, or user-facing session logic.
- **FR-011**: The internal place schema MUST be source-agnostic. Field names, structure, and semantics MUST be defined in terms of the internal domain model, not derived from or dependent on Google Places API response shapes. This allows future data sources to be added without schema changes.

### Key Entities *(include if feature involves data)*

- **Place**: The normalized internal representation of a location. Contains all fields needed for display or filtering: identifying information (name, address, coordinates, district), classification (primary type, full types list), operational data (rating, business status, hours, contact), derived classification fields useful for filtering (indoor/outdoor, budget level), and service-level scoring fields (trend score, confidence score). Uniquely identified by `google_place_id`. Fields are defined in the internal domain model, independent of any external source schema.
- **Google Place Source**: A raw, unmodified payload received from a Google Places data ingestion. Linked to a Place record. Preserved as-is to enable future remapping, debugging, or reprocessing without data loss.
- **Place Features**: Extended audience and context ranking scores associated with a Place, consumed exclusively by downstream recommendation and ranking systems. Not used for direct filtering or display. Includes scores such as couple suitability, family suitability, food relevance, cultural relevance, rainy-day suitability, crowd level, transport accessibility, photo quality, and hidden-gem likelihood. Also carries an open-ended feature dictionary for future extensibility. Score values may be null initially.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A downstream service can retrieve a filtered list of places in a single request without requiring knowledge of the internal storage format.
- **SC-002**: A place ingested from a raw Google Places payload is immediately queryable through the retrieval endpoints after the ingestion request completes.
- **SC-003**: Resubmitting the same `google_place_id` payload does not create duplicate records; the existing record is updated.
- **SC-004**: The health endpoint responds correctly under normal conditions and reports an unhealthy state when the database is unreachable.
- **SC-005**: A developer can seed the database and verify a complete round-trip (ingest → store → retrieve) using only the service's own endpoints and the seed script.
- **SC-006**: Ingestion of a payload with missing optional fields does not produce an error; the place record is created with the available data.

## Assumptions

- The database instance is already provisioned and accessible to the service; the service does not manage database infrastructure.
- The Google Places data ingested by this service is pre-fetched by an external process; this service does not call the Google Places API directly in the initial implementation.
- The `google_place_id` field is always present in valid Google Places payloads and serves as the canonical deduplication key.
- Derived feature scores (couple score, family score, etc.) are computed externally and written to the service; the service stores and serves them but does not compute them.
- No authentication or access control is required for the initial implementation; the service is assumed to run in a trusted network context.
- Multiple downstream backends may call this service concurrently; the service must handle concurrent reads safely.
- JSONB storage is appropriate for fields with nested or variable-length structure (types list, opening hours, raw payloads, feature dictionaries).
- Schema migration tooling will be added later; initial development may use auto-creation of tables on startup.
- No crawler, social review pipeline, or live third-party data polling is in scope for this milestone.
- The current milestone targets local development correctness only; production readiness concerns (performance targets, SLAs, observability infrastructure) are deferred.
