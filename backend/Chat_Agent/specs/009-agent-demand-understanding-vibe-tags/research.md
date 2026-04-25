# Research: Constraint-Aware Demand Understanding and Database-Backed Vibe Tags

**Date**: 2026-04-24  
**Feature**: `009-agent-demand-understanding-vibe-tags`

## Research Questions

1. Should natural-language stop references be solved with a larger regex parser or LLM structured extraction?
2. Where should vibe vocabulary live?
3. How should new turn constraints interact with session preferences?
4. How should replanning reuse cached candidates safely?
5. How should mixed-category itineraries be generated?

## Decision 1: Regex Is Fast Path, Not Source of Truth

**Decision**: Use regex only for high-confidence common phrases. Use an LLM structured extractor for broader wording, then validate output deterministically.

**Rationale**:

- User phrasing is open-ended: "second one", "the one after lunch", "that restaurant", "剛剛那間", "最後那個".
- Expanding regex coverage will keep missing cases and increases maintenance cost.
- LLM can map natural language to structure, but should not directly mutate state.

**Rejected Alternative**: Keep adding regex patterns for every observed phrase.  
**Why rejected**: It scales poorly and still cannot handle contextual references reliably.

## Decision 2: Vibe Tags Come From the Data Service

**Decision**: Data Service exposes a known tag catalog. Chat_Agent fetches it and allows the LLM to choose only from that catalog.

**Rationale**:

- `vibe_tags` are produced by social ingestion and aggregation.
- The available set changes as data changes.
- Hardcoded Chat_Agent mappings will drift from the database.

**Rejected Alternative**: Maintain a static `romantic/fun/cozy/...` mapping in Chat_Agent.  
**Why rejected**: It cannot cover all known tags and may send filters that return no data.

## Decision 3: Separate Stable Preferences From Turn Constraints

**Decision**: Introduce `TurnIntentFrame` for current-turn execution and keep `Preferences` for long-lived session memory.

**Rationale**:

- A request like "third stop to a park" is a replacement constraint, not a global interest preference.
- A later request like "romantic Japanese restaurant" should not inherit the old park constraint.
- Stable fields such as origin, district, time window, transport, and language should persist.

**Rejected Alternative**: Store everything in `Preferences.interest_tags`.  
**Why rejected**: It caused old interests to pollute later requests.

## Decision 4: Cache Reuse Requires Constraint Matching

**Decision**: Replanning can reuse cached candidates only after `candidate_matches_constraint` succeeds.

**Rationale**:

- Cached candidates are useful for speed.
- But cached candidates often reflect the previous query, not the new replacement request.
- A food candidate must never satisfy "replace with a park".

**Rejected Alternative**: Always pick the first unused cached candidate.  
**Why rejected**: This is the observed root cause of replacing attraction requests with restaurants.

## Decision 5: Mixed Itinerary Requires Multi-Query Retrieval

**Decision**: Detect category mix and run one retrieval per requested category, then select a diverse itinerary pattern.

**Rationale**:

- A single `internal_category=food` query cannot satisfy "play and eat".
- A single broad query sorted by rating often clusters one category.
- Diversity must be enforced after retrieval.

**Rejected Alternative**: Ask the LLM to pick diverse stops from one candidate list.  
**Why rejected**: If the candidate list lacks one category, the LLM cannot fix it and may hallucinate diversity.

## Open Questions

- Should Data Service recommend support strict `vibe_tags`, or should Chat_Agent route all vibe requests through search?
- Should `vibe_tag` filters use AND semantics only, or should Chat_Agent support OR semantics through multiple searches?
- Should `category_mix` preserve user order, or should itinerary ordering be optimized by routing distance?
- How should named-stop references be resolved when multiple stops have similar names?

## Current Recommendation

Start with strict, testable behavior:

- Data Service returns known tags.
- LLM selects known tags only.
- Search supports repeated `vibe_tag` AND semantics, with relaxation if empty.
- Recommend can be extended later for richer scenario ranking, but Chat_Agent can initially use search fallback for vibe requests.
