# ChitoGo DataBase Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-18

## Active Technologies

- **001-place-data-service**: Python 3.11+, FastAPI, SQLAlchemy 2.x, PostgreSQL 12, psycopg2-binary, pydantic-settings, uvicorn
- **002-llm-place-retrieval-apis**: Same stack; adds `app/services/category.py`, `app/schemas/retrieval.py`, `app/routers/retrieval.py`; no new pip dependencies

## Project Structure

```text
app/
├── main.py
├── db.py
├── core/config.py
├── models/          # Place, PlaceSourceGoogle, PlaceFeatures ORM models
├── routers/         # health.py, places.py, retrieval.py (002)
├── schemas/         # place.py, retrieval.py (002)
└── services/        # ingestion.py, category.py (002)

scripts/
├── seed.py
└── migrate_add_internal_category.py   # 002 — adds internal_category column

specs/
├── 001-place-data-service/   # spec, plan, research, data-model, contracts
└── 002-llm-place-retrieval-apis/   # spec, plan, data-model, contracts, tasks
```

## Commands

```bash
# Install
pip install -r requirements.txt

# Run service (auto-creates tables on startup)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Seed sample data
python scripts/seed.py

# 002: Add internal_category column + backfill existing rows
python scripts/migrate_add_internal_category.py

# Health check
curl http://localhost:8000/api/v1/health/db

# District filter verification
curl "http://localhost:8000/api/v1/places?district=中正區"

# 002: LLM retrieval APIs
curl "http://localhost:8000/api/v1/places/search?internal_category=attraction"
curl "http://localhost:8000/api/v1/places/nearby?lat=25.0441&lng=121.5292&radius_m=1000"
curl "http://localhost:8000/api/v1/places/stats"
curl "http://localhost:8000/api/v1/places/categories"
```

## Code Style

- Python: follow PEP 8; SQLAlchemy 2.x `DeclarativeBase` style
- pydantic-settings v2: use `model_config` dict (not inner `Config` class)
- All models must be imported in `app/models/__init__.py` before `create_all`
- Use `JSONB` from `sqlalchemy.dialects.postgresql` for nested/variable fields
- Naming convention: `chitogo_` prefix for DB user/database

## Database

- Host: localhost:5432
- Database: chitogo
- User: chitogo_user
- URL: `postgresql://chitogo_user:kawairoha@localhost:5432/chitogo`
- Schema management: `Base.metadata.create_all()` on startup (Alembic deferred)

## Recent Changes

- 001-place-data-service: Initial plan — place data service with ingestion, normalization, storage, retrieval
- 001-place-data-service: Seed/verification flow aligned to Taipei sample place `華山1914文化創意產業園區`
- 002-llm-place-retrieval-apis: Spec + plan + tasks — LLM-friendly search, nearby, batch, recommend, stats APIs; adds `internal_category` column to places

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
