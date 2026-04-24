# Chat_Agent Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-20

## Active Technologies

- Python 3.11 + FastAPI 0.111, Pydantic v2, httpx (for Data Service + Google Maps calls), Anthropic SDK (Claude for the agent loop), uvicorn (003-agent-orchestration-backend)

## Project Structure

```text
src/
tests/
```

## Commands

cd src && pytest && ruff check .

## Code Style

Python 3.11: Follow standard conventions

## Recent Changes

- 003-agent-orchestration-backend: Added Python 3.11 + FastAPI 0.111, Pydantic v2, httpx (for Data Service + Google Maps calls), Anthropic SDK (Claude for the agent loop), uvicorn

<!-- MANUAL ADDITIONS START -->
- 003-social-crawl-ingestion Phase 4: `PlaceToolAdapter.search_places()` now accepts `vibe_tags` and `min_mentions`, forwards repeated `vibe_tag` query params to the Data Service, and supports the social sorts `mention_count_desc`, `trend_score_desc`, and `sentiment_desc`.
- `ToolPlace` now exposes optional social summary fields from the Data Service: `vibe_tags`, `mention_count`, and `sentiment_score`.
<!-- MANUAL ADDITIONS END -->
