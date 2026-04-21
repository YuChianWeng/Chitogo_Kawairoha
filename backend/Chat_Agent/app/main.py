from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.chat.message_handler import MessageHandler
from app.chat.trace_store import TraceStore
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.session.manager import session_manager
from app.session.store import session_store
from app.session.sweeper import stop_ttl_sweeper, ttl_sweeper_loop
from app.tools.place_adapter import place_tool_adapter
from app.tools.registry import tool_registry
from app.tools.route_adapter import route_tool_adapter


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory for the agent orchestration backend."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ttl_sweeper_task = asyncio.create_task(
            ttl_sweeper_loop(
                store=session_store,
                ttl_minutes=app_settings.session_ttl_minutes,
            )
        )
        try:
            yield
        finally:
            await stop_ttl_sweeper(app.state.ttl_sweeper_task)
            app.state.ttl_sweeper_task = None

    app = FastAPI(
        title="Chitogo Chat Agent",
        version="0.1.0",
        description="Main orchestration backend for the Taipei travel AI assistant.",
        lifespan=lifespan,
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
    app.state.session_store = session_store
    app.state.session_manager = session_manager
    app.state.place_tool_adapter = place_tool_adapter
    app.state.route_tool_adapter = route_tool_adapter
    app.state.tool_registry = tool_registry
    app.state.trace_store = TraceStore(max_items=app_settings.trace_store_max_items)
    app.state.message_handler = MessageHandler(
        settings=app_settings,
        trace_store=app.state.trace_store,
    )
    app.state.ttl_sweeper_task = None
    return app


app = create_app()
