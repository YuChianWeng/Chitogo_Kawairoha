from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from app.session.models import Itinerary, Place, Preferences, Session, Turn, utc_now
from app.session.store import InMemorySessionStore, session_store


class InvalidSessionIdError(ValueError):
    """Raised when the provided session identifier is not a valid UUID."""


def merge_preferences(current: Preferences, delta: Preferences) -> Preferences:
    """Merge a partial preferences update into the current preferences object."""
    merged_data = current.model_dump()
    for field_name in delta.model_fields_set:
        merged_data[field_name] = getattr(delta, field_name)
    return Preferences.model_validate(merged_data)


class SessionManager:
    """Primary mutation API for session state."""

    def __init__(self, store: InMemorySessionStore | None = None) -> None:
        self._store = store or session_store

    def _normalize_session_id(self, session_id: str) -> str:
        try:
            return str(UUID(session_id))
        except (TypeError, ValueError) as exc:
            raise InvalidSessionIdError("session_id must be a valid UUID") from exc

    async def get_or_create(self, session_id: str) -> Session:
        normalized_session_id = self._normalize_session_id(session_id)
        now = utc_now()

        def create_session() -> Session:
            return Session(
                session_id=normalized_session_id,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )

        def touch_session(session: Session) -> None:
            session.last_activity_at = now

        return await self._store.upsert(
            normalized_session_id,
            create_session=create_session,
            mutate=touch_session,
        )

    async def touch(self, session_id: str) -> Session:
        normalized_session_id = self._normalize_session_id(session_id)
        touched = await self._store.touch(normalized_session_id, activity_at=utc_now())
        if touched is not None:
            return touched
        return await self.get_or_create(normalized_session_id)

    async def append_turn(self, session_id: str, turn: Turn) -> Session:
        normalized_session_id = self._normalize_session_id(session_id)
        now = utc_now()
        turn_copy = turn.model_copy(deep=True)

        def create_session() -> Session:
            return Session(
                session_id=normalized_session_id,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )

        def add_turn(session: Session) -> None:
            session.turns.append(turn_copy.model_copy(deep=True))
            session.updated_at = now
            session.last_activity_at = now

        return await self._store.upsert(
            normalized_session_id,
            create_session=create_session,
            mutate=add_turn,
        )

    async def update_preferences(self, session_id: str, preferences_delta: Preferences) -> Session:
        normalized_session_id = self._normalize_session_id(session_id)
        now = utc_now()
        delta_copy = preferences_delta.model_copy(deep=True)

        def create_session() -> Session:
            return Session(
                session_id=normalized_session_id,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )

        def apply_preferences(session: Session) -> None:
            session.preferences = merge_preferences(session.preferences, delta_copy)
            session.updated_at = now
            session.last_activity_at = now

        return await self._store.upsert(
            normalized_session_id,
            create_session=create_session,
            mutate=apply_preferences,
        )

    async def set_itinerary(self, session_id: str, itinerary: Itinerary) -> Session:
        normalized_session_id = self._normalize_session_id(session_id)
        now = utc_now()
        itinerary_copy = itinerary.model_copy(deep=True)

        def create_session() -> Session:
            return Session(
                session_id=normalized_session_id,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )

        def assign_itinerary(session: Session) -> None:
            session.latest_itinerary = itinerary_copy.model_copy(deep=True)
            session.updated_at = now
            session.last_activity_at = now

        return await self._store.upsert(
            normalized_session_id,
            create_session=create_session,
            mutate=assign_itinerary,
        )

    async def cache_candidates(self, session_id: str, candidates: list[Place]) -> Session:
        normalized_session_id = self._normalize_session_id(session_id)
        now = utc_now()
        candidate_copies = [candidate.model_copy(deep=True) for candidate in candidates]

        def create_session() -> Session:
            return Session(
                session_id=normalized_session_id,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )

        def assign_candidates(session: Session) -> None:
            session.cached_candidates = [
                candidate.model_copy(deep=True) for candidate in candidate_copies
            ]
            session.updated_at = now
            session.last_activity_at = now

        return await self._store.upsert(
            normalized_session_id,
            create_session=create_session,
            mutate=assign_candidates,
        )

    def is_expired(self, session: Session, ttl_minutes: int) -> bool:
        return utc_now() - session.last_activity_at > timedelta(minutes=ttl_minutes)


session_manager = SessionManager()
