from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.db import init_db, seed_from_json
from app.api.v1.router import router as v1_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_SEED_FILE = Path(__file__).parent / "data" / "venues.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialise DB and seed venues
    await init_db()
    await seed_from_json(str(_SEED_FILE))
    logger.info("Application startup complete")
    yield
    # Shutdown (nothing to clean up for SQLite)
    logger.info("Application shutdown")


app = FastAPI(
    title="Taipei Itinerary Planner API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    msg = str(exc)
    # Extract error code from messages like "code: description"
    code = "validation_error"
    if ":" in msg:
        code = msg.split(":")[0].strip()
    return JSONResponse(
        status_code=400,
        content={"status": "error", "code": code, "message": msg},
    )
