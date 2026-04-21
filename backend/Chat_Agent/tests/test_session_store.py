from __future__ import annotations

import asyncio
import unittest
from datetime import timedelta
from uuid import uuid4

from app.session.models import Session, utc_now
from app.session.store import InMemorySessionStore
from app.session.sweeper import sweep_expired_sessions


class SessionStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = InMemorySessionStore()

    async def asyncTearDown(self) -> None:
        await self.store.clear()

    async def test_store_crud_and_all_session_ids(self) -> None:
        session_a = Session(session_id=str(uuid4()))
        session_b = Session(session_id=str(uuid4()))

        await self.store.set(session_a)
        await self.store.set(session_b)

        stored_a = await self.store.get(session_a.session_id)
        session_ids = await self.store.all_session_ids()

        self.assertIsNotNone(stored_a)
        self.assertCountEqual(session_ids, [session_a.session_id, session_b.session_id])

        await self.store.delete(session_a.session_id)
        self.assertIsNone(await self.store.get(session_a.session_id))

    async def test_ttl_sweeper_evicts_expired_sessions(self) -> None:
        now = utc_now()
        expired = Session(
            session_id=str(uuid4()),
            created_at=now - timedelta(minutes=40),
            updated_at=now - timedelta(minutes=40),
            last_activity_at=now - timedelta(minutes=31),
        )
        active = Session(
            session_id=str(uuid4()),
            created_at=now - timedelta(minutes=5),
            updated_at=now - timedelta(minutes=5),
            last_activity_at=now - timedelta(minutes=5),
        )

        await self.store.set(expired)
        await self.store.set(active)

        evicted = await sweep_expired_sessions(self.store, ttl_minutes=30)

        self.assertEqual(evicted, [expired.session_id])
        self.assertIsNone(await self.store.get(expired.session_id))
        self.assertIsNotNone(await self.store.get(active.session_id))

    async def test_concurrent_sets_keep_sessions_isolated(self) -> None:
        session_ids = [str(uuid4()) for _ in range(100)]

        async def put_session(session_id: str) -> None:
            await self.store.set(Session(session_id=session_id))

        await asyncio.gather(*(put_session(session_id) for session_id in session_ids))

        stored_ids = await self.store.all_session_ids()
        self.assertCountEqual(stored_ids, session_ids)
