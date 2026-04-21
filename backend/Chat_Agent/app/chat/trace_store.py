from __future__ import annotations

import asyncio
import logging
from collections import deque

from app.chat.schemas import ChatTraceDetail, ChatTraceSummary
from app.core.logging import log_event

logger = logging.getLogger(__name__)


class TraceStore:
    """Async-safe bounded in-memory store for recent request traces."""

    def __init__(self, *, max_items: int = 200) -> None:
        self._max_items = max_items
        self._traces: dict[str, ChatTraceDetail] = {}
        self._order: deque[str] = deque()
        self._lock = asyncio.Lock()

    async def add(self, trace: ChatTraceDetail) -> None:
        evicted_ids: list[str] = []
        async with self._lock:
            if trace.trace_id in self._traces:
                try:
                    self._order.remove(trace.trace_id)
                except ValueError:
                    pass
            self._traces[trace.trace_id] = trace.model_copy(deep=True)
            self._order.appendleft(trace.trace_id)
            while len(self._order) > self._max_items:
                evicted_trace_id = self._order.pop()
                self._traces.pop(evicted_trace_id, None)
                evicted_ids.append(evicted_trace_id)

        for evicted_trace_id in evicted_ids:
            log_event(
                logger,
                logging.WARNING,
                "trace.evicted",
                trace_id=evicted_trace_id,
                max_items=self._max_items,
            )

    async def get(self, trace_id: str) -> ChatTraceDetail | None:
        async with self._lock:
            trace = self._traces.get(trace_id)
            return trace.model_copy(deep=True) if trace is not None else None

    async def list_recent(
        self,
        *,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[ChatTraceSummary]:
        async with self._lock:
            items: list[ChatTraceSummary] = []
            for trace_id in self._order:
                trace = self._traces.get(trace_id)
                if trace is None:
                    continue
                if session_id is not None and trace.session_id != session_id:
                    continue
                items.append(ChatTraceSummary.from_trace(trace))
                if len(items) >= limit:
                    break
            return [item.model_copy(deep=True) for item in items]

    async def clear(self) -> None:
        async with self._lock:
            self._traces.clear()
            self._order.clear()


__all__ = ["TraceStore"]
