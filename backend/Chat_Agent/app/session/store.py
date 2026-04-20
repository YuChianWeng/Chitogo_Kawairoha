from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from app.session.models import Session, utc_now


class InMemorySessionStore:
    """Async-safe in-memory store for session state."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> Session | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            return session.model_copy(deep=True) if session is not None else None

    async def set(self, session: Session) -> Session:
        async with self._lock:
            stored = session.model_copy(deep=True)
            self._sessions[session.session_id] = stored
            return stored.model_copy(deep=True)

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def all_session_ids(self) -> list[str]:
        async with self._lock:
            return list(self._sessions.keys())

    async def clear(self) -> None:
        async with self._lock:
            self._sessions.clear()

    async def touch(self, session_id: str, activity_at: datetime | None = None) -> Session | None:
        timestamp = activity_at or utc_now()
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.last_activity_at = timestamp
            return session.model_copy(deep=True)

    async def upsert(
        self,
        session_id: str,
        create_session: Callable[[], Session],
        mutate: Callable[[Session], None] | None = None,
    ) -> Session:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = create_session().model_copy(deep=True)
            else:
                session = session.model_copy(deep=True)

            if mutate is not None:
                mutate(session)

            self._sessions[session_id] = session.model_copy(deep=True)
            return session.model_copy(deep=True)

    async def delete_expired(self, cutoff: datetime) -> list[str]:
        async with self._lock:
            expired_session_ids = [
                session_id
                for session_id, session in self._sessions.items()
                if session.last_activity_at < cutoff
            ]
            for session_id in expired_session_ids:
                self._sessions.pop(session_id, None)
            return expired_session_ids


session_store = InMemorySessionStore()
