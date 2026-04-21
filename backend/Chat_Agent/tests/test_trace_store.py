from __future__ import annotations

import asyncio
import unittest

from app.chat.schemas import ChatTraceDetail
from app.chat.trace_store import TraceStore
from app.session.models import utc_now


def build_trace(trace_id: str, *, session_id: str = "session-a") -> ChatTraceDetail:
    return ChatTraceDetail(
        trace_id=trace_id,
        session_id=session_id,
        requested_at=utc_now(),
        intent="GENERATE_ITINERARY",
        needs_clarification=False,
        final_status="success",
        outcome="itinerary_generated",
        duration_ms=5,
    )


class TraceStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = TraceStore(max_items=2)

    async def asyncTearDown(self) -> None:
        await self.store.clear()

    async def test_trace_store_evicts_oldest_entries(self) -> None:
        await self.store.add(build_trace("trace-1"))
        await self.store.add(build_trace("trace-2"))
        await self.store.add(build_trace("trace-3"))

        recent = await self.store.list_recent(limit=10)

        self.assertEqual([item.trace_id for item in recent], ["trace-3", "trace-2"])
        self.assertIsNone(await self.store.get("trace-1"))

    async def test_trace_store_filters_by_session_id(self) -> None:
        await self.store.add(build_trace("trace-1", session_id="session-a"))
        await self.store.add(build_trace("trace-2", session_id="session-b"))

        recent = await self.store.list_recent(limit=10, session_id="session-b")

        self.assertEqual([item.trace_id for item in recent], ["trace-2"])

    async def test_trace_store_handles_concurrent_writes(self) -> None:
        completion_order: list[str] = []
        completion_lock = asyncio.Lock()

        async def put_trace(index: int) -> None:
            trace_id = f"trace-{index}"
            await self.store.add(build_trace(trace_id, session_id=f"session-{index}"))
            async with completion_lock:
                completion_order.append(trace_id)

        await asyncio.gather(*(put_trace(index) for index in range(10)))
        recent = await self.store.list_recent(limit=10)

        self.assertEqual(len(recent), 2)
        expected_recent_ids = list(reversed(completion_order[-2:]))
        self.assertEqual([item.trace_id for item in recent], expected_recent_ids)
