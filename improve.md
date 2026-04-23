# Chat_Agent Improvement Notes

## Purpose

This document summarizes practical ways to improve the current `backend/Chat_Agent` architecture, especially around repeated extraction, tool orchestration, and recommendation quality.

It is written as an analysis aid, not as a final implementation spec.

## Current Shape

Today the request flow is roughly:

1. `MessageHandler` receives the user message.
2. `IntentClassifier` classifies the message.
3. `PreferenceExtractor` extracts session-level preferences.
4. The merged preferences are re-checked for missing fields.
5. `AgentLoop` decides which tool to call and with what parameters.
6. `ResponseComposer` turns tool results into user-facing text.

Core files:

- `backend/Chat_Agent/app/chat/message_handler.py`
- `backend/Chat_Agent/app/orchestration/classifier.py`
- `backend/Chat_Agent/app/orchestration/preferences.py`
- `backend/Chat_Agent/app/chat/loop.py`
- `backend/Chat_Agent/app/chat/response_composer.py`

## What Is Good About The Current Design

- Deterministic control is fairly strong.
- Session state is explicit and testable.
- Tool calling is bounded by code, not by model free-form behavior.
- Fallback and trace behavior are easier to reason about than in a fully agentic design.
- Unit testing is straightforward because responsibilities are separated.

## Main Problems

### 1. The same message is interpreted multiple times

The system currently asks the model or the parser to understand one user message in several separate passes:

- classification
- preference extraction
- missing-field detection
- tool planning

This creates inconsistency risk. One pass may understand `日式餐廳`, another may reduce it to generic `food`, and another may miss it entirely.

### 2. Too much semantic drift between layers

The intent layer, preference layer, and tool-planning layer each have their own normalization logic. This means subtle meaning can be lost between:

- raw user wording
- normalized preferences
- tool parameters

### 3. Prompt quality matters too much at too many stages

Because multiple model calls are involved, prompt fragility compounds. Small extraction mistakes propagate downstream.

### 4. The system is not fully agentic, but it still pays some multi-step complexity costs

It has several model-driven steps, but not the full benefit of a proper agent runtime:

- no true iterative reasoning loop
- no generalized tool error recovery loop
- no unified planner/executor state machine

So it gets part of the complexity of an agent without fully gaining agent flexibility.

## Your Main Question

Why not just tell the model everything it can do, define it as a tour guide, give it tools, and let it reason until it succeeds or decides it cannot?

The short answer:

You can. But that is a different architecture.

That design is not just "better prompting". It requires an external runtime that controls:

- tool schemas
- retry limits
- stopping conditions
- validation
- loop budgets
- state updates
- trace logging
- user clarification thresholds

Products like Claude Code or Codex feel like "the model just does it", but in practice there is a significant orchestration layer around the model.

## Three Realistic Paths

## Option A: Keep Current Architecture, But Reduce Friction

This is the lowest-risk path.

### What to change

- Merge duplicate extraction heuristics where possible.
- Expand message-level fallback extraction for important business signals.
- Reduce repeated model calls where deterministic logic is sufficient.
- Tighten normalization rules so fewer meanings are lost between layers.

### Pros

- Lowest implementation risk.
- Preserves current tests and mental model.
- Good fit if reliability matters more than flexibility.

### Cons

- Core duplication problem remains.
- Future complexity will keep accumulating.
- Harder to improve "naturalness" without adding more patches.

### Best for

- Teams that want incremental quality gains without changing the control model.

## Option B: Hybrid Architecture With One Understanding Pass

This is the architecture I would recommend first.

### Idea

Replace multiple early understanding passes with one structured model call that returns something like:

```json
{
  "intent": "GENERATE_ITINERARY",
  "needs_clarification": false,
  "missing_fields": [],
  "preference_delta": {
    "district": "大安區",
    "time_window": {"start_time": "13:00", "end_time": "18:00"},
    "companions": "friends",
    "interest_tags": ["日式", "咖啡廳"]
  },
  "planning_hints": {
    "query_mode": "search",
    "primary_type_candidates": ["japanese_restaurant", "coffee_shop"]
  }
}
```

Then keep the downstream tool execution deterministic.

### What stays deterministic

- session merge
- tool registry access
- tool parameter validation
- fallback ladder
- response composition

### What improves

- one message gets one semantic interpretation instead of many
- fewer inconsistent states
- fewer repeated prompts
- simpler debugging when meaning is lost

### Pros

- Strong improvement in coherence without losing control.
- Easier migration path from current code.
- Still highly testable.

### Cons

- Requires redesign of message understanding contracts.
- Some current modules become thinner or partially redundant.

### Best for

- Product backends that need both control and better natural language robustness.

## Option C: Full Agent Loop

This is closest to the "tour guide with tools" model you described.

### Idea

The model becomes the main planner:

1. Read the user message and current session state.
2. Decide what tool to call.
3. Call the tool.
4. Inspect the tool result or tool error.
5. Retry with adjusted params if appropriate.
6. Stop when enough information is available or when clarification is required.

### Requirements beyond prompting

- strict step limit, for example `max_steps=4`
- tool-call validator
- retry policy per tool
- typed error feedback to the model
- loop budget and timeout budget
- guardrails for when to ask the user instead of retrying
- replayable trace storage

### Pros

- Most flexible.
- Best for complex or ambiguous requests.
- Can adapt more naturally when tool output is unexpected.

### Cons

- Highest cost and latency.
- Harder to guarantee behavior.
- Harder to test deterministically.
- Easier to get stuck in low-value retry loops.
- More difficult to reason about session updates and user-facing consistency.

### Best for

- High-value assistant workflows where flexibility matters more than strict predictability.

## Recommended Direction

Recommend **Option B: Hybrid One-Pass Understanding + Deterministic Execution**.

Reason:

- It addresses the biggest current issue: repeated interpretation of the same user message.
- It does not throw away the parts of the current system that are already working well.
- It avoids the operational complexity of a full agent loop too early.

## Suggested Refactor Plan

## Phase 1: Introduce a Unified Understanding Contract

Create a new module, for example:

- `app/orchestration/understanding.py`

Return one typed object that contains:

- intent
- preference delta
- clarification needs
- planning hints

At this stage, keep current classifier and preference extractor as fallback only.

## Phase 2: Move Missing-Field Detection Into The Same Understanding Result

Remove the separate generate-time missing-field pass where possible.

This reduces cases where:

- classifier says "enough info"
- merged preferences say "not enough info"

## Phase 3: Make Tool Planning More Explicit

The model should propose planning hints, not raw free-form behavior.

Examples:

- preferred tool family
- candidate place types
- whether this is a strict search or broad recommendation request

The code should still decide the final validated tool call.

## Phase 4: Add Limited Tool Replanning

Before adopting a full agent loop, add a narrow retry layer:

- first tool call fails or returns empty
- one model-assisted replanning pass is allowed
- second call runs with validated params

This captures much of the benefit of agentic recovery without open-ended loops.

## Phase 5: Re-evaluate Whether Full Agenticity Is Still Needed

Only after measuring the hybrid system should the team decide whether a full agent loop is worth the cost.

## What Not To Do

- Do not simply add more prompt text to the current many-step flow and expect consistency to improve.
- Do not let the model freely mutate session state without validation.
- Do not add unlimited retry loops around tool calls.
- Do not mix user-facing prose generation with hidden orchestration reasoning in one uncontrolled pass.

## Specific Improvement Opportunities In This Repo

### A. Create one canonical meaning representation

Today, meaning is split across:

- `ClassifierResult`
- `Preferences`
- `LoopResult`

Add a dedicated typed contract for "what this user message means right now".

### B. Separate durable preferences from turn-local intent

Some information should persist across turns, some should not.

Examples:

- durable: transport mode, budget preference, language
- turn-local: this request wants `日式餐廳` first, nearby now, replace stop 2

This distinction should be explicit in code.

### C. Make domain-specific type hints first-class

Cuisine and venue-type hints should not depend on generic tags surviving multiple layers.

Examples:

- `日式餐廳`
- `拉麵`
- `居酒屋`
- `咖啡廳`

These should be preserved early and mapped once.

### D. Make tool failures typed and actionable

Instead of just `error` or `empty`, classify failures into:

- validation error
- upstream service error
- no results under strict filters
- no results even after relaxation
- user clarification required

This makes both deterministic and agentic retries safer.

### E. Add architecture-level metrics

Track:

- clarification rate
- empty-result rate before and after relaxations
- retry rate
- tool error rate by tool
- "meaning lost" cases, for example specific cuisine requested but generic category used

## Evaluation Questions

Before choosing the next architecture, answer these:

1. Is current user dissatisfaction mainly caused by semantic inconsistency or by weak retrieval quality?
2. Is latency budget tight enough that extra model loops are unacceptable?
3. Does the product need strong reproducibility for debugging and ops?
4. Is the team prepared to operate a real agent runtime, not just longer prompts?
5. Is session memory a first-class product requirement?

## Practical Recommendation

If the goal is better product behavior soon:

1. Build unified understanding first.
2. Keep deterministic execution.
3. Add only bounded replanning around tool failures.
4. Delay full agent loops until metrics prove they are necessary.

If the goal is maximum flexibility and you accept higher cost, higher latency, and harder debugging:

1. Build a real planner-executor runtime.
2. Make the model responsible for tool sequencing.
3. Enforce strict loop and validation guardrails outside the model.

## Bottom Line

The current architecture is not wrong. It is a reasonable product-backend design.

Its main weakness is not "it uses multiple modules". Its main weakness is that the same user message is understood too many times by different components.

The best next step is usually not "prompt harder".

The best next step is:

- fewer semantic passes
- one canonical understanding object
- deterministic execution around tools
- optional bounded replanning, not unlimited agent loops
