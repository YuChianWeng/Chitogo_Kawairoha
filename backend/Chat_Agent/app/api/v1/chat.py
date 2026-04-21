from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi import Query
from fastapi.responses import JSONResponse

from app.chat.message_handler import MessageHandler
from app.chat.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatTraceDetail,
    ChatTraceListResponse,
    ErrorEnvelope,
)
from app.chat.trace_store import TraceStore
from app.core.logging import log_event
from app.session.manager import InvalidSessionIdError

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def get_message_handler(request: Request) -> MessageHandler:
    return request.app.state.message_handler


def get_trace_store(request: Request) -> TraceStore:
    return request.app.state.trace_store


@router.post("/message", response_model=ChatMessageResponse)
async def post_chat_message(
    payload: ChatMessageRequest,
    handler: MessageHandler = Depends(get_message_handler),
) -> ChatMessageResponse | JSONResponse:
    try:
        return await handler.handle(payload)
    except InvalidSessionIdError as exc:
        log_event(
            logger,
            logging.WARNING,
            "chat.request.invalid_session",
            session_id=payload.session_id,
            error=exc.__class__.__name__,
        )
        error = ErrorEnvelope(error="invalid_session_id", detail=str(exc))
        return JSONResponse(status_code=400, content=error.model_dump())
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "chat.request.unhandled_error",
            session_id=payload.session_id,
            error=exc.__class__.__name__,
        )
        error = ErrorEnvelope(error="internal_error")
        return JSONResponse(status_code=500, content=error.model_dump())


@router.get("/traces", response_model=ChatTraceListResponse)
async def list_chat_traces(
    limit: int = Query(default=20, ge=1, le=200),
    session_id: str | None = Query(default=None),
    trace_store: TraceStore = Depends(get_trace_store),
) -> ChatTraceListResponse:
    return ChatTraceListResponse(
        items=await trace_store.list_recent(limit=limit, session_id=session_id),
    )


@router.get("/traces/{trace_id}", response_model=ChatTraceDetail)
async def get_chat_trace(
    trace_id: str,
    trace_store: TraceStore = Depends(get_trace_store),
) -> ChatTraceDetail | JSONResponse:
    trace = await trace_store.get(trace_id)
    if trace is None:
        error = ErrorEnvelope(error="trace_not_found", detail="trace_id was not found")
        return JSONResponse(status_code=404, content=error.model_dump())
    return trace
