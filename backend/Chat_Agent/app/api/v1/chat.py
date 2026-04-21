from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.chat.message_handler import MessageHandler
from app.chat.schemas import ChatMessageRequest, ChatMessageResponse, ErrorEnvelope
from app.session.manager import InvalidSessionIdError

router = APIRouter(prefix="/chat", tags=["chat"])


def get_message_handler(request: Request) -> MessageHandler:
    return request.app.state.message_handler


@router.post("/message", response_model=ChatMessageResponse)
async def post_chat_message(
    payload: ChatMessageRequest,
    handler: MessageHandler = Depends(get_message_handler),
) -> ChatMessageResponse | JSONResponse:
    try:
        return await handler.handle(payload)
    except InvalidSessionIdError as exc:
        error = ErrorEnvelope(error="invalid_session_id", detail=str(exc))
        return JSONResponse(status_code=400, content=error.model_dump())
    except Exception:
        error = ErrorEnvelope(error="internal_error")
        return JSONResponse(status_code=500, content=error.model_dump())
