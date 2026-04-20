from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory for the agent orchestration backend."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title="Chitogo Chat Agent",
        version="0.1.0",
        description="Main orchestration backend for the Taipei travel AI assistant.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v1_router, prefix="/api/v1")
    app.state.settings = app_settings
    return app


app = create_app()
