from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4

from app.session.manager import InvalidSessionIdError, SessionManager
from app.session.models import Itinerary, Leg, Place, Preferences, Stop, Turn
from app.session.store import InMemorySessionStore


def build_turn(turn_id: str, content: str) -> Turn:
    return Turn(turn_id=turn_id, role="user", content=content)


def build_itinerary() -> Itinerary:
    return Itinerary(
        summary="Two-stop route",
        total_duration_min=80,
        stops=[
            Stop(
                stop_index=0,
                venue_id=1,
                venue_name="Stop A",
                category="attraction",
                arrival_time="10:00",
                visit_duration_min=45,
                lat=25.0,
                lng=121.5,
            ),
            Stop(
                stop_index=1,
                venue_id=2,
                venue_name="Stop B",
                category="food",
                arrival_time="11:05",
                visit_duration_min=25,
                lat=25.1,
                lng=121.6,
            ),
        ],
        legs=[
            Leg(
                from_stop=0,
                to_stop=1,
                transit_method="transit",
                duration_min=10,
                estimated=False,
            )
        ],
    )


class SessionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = InMemorySessionStore()
        self.manager = SessionManager(store=self.store)

    async def asyncTearDown(self) -> None:
        await self.store.clear()

    async def test_get_or_create_returns_same_session_for_same_id(self) -> None:
        session_id = str(uuid4())

        session_one = await self.manager.get_or_create(session_id)
        session_two = await self.manager.get_or_create(session_id)

        self.assertEqual(session_one.session_id, session_two.session_id)
        self.assertEqual(session_one.created_at, session_two.created_at)
        self.assertGreaterEqual(session_two.last_activity_at, session_one.last_activity_at)

    async def test_different_session_ids_do_not_share_state(self) -> None:
        session_a = str(uuid4())
        session_b = str(uuid4())

        await self.manager.update_preferences(
            session_a,
            Preferences(companions="friends", interest_tags=["night-market"]),
        )
        untouched = await self.manager.get_or_create(session_b)

        self.assertIsNone(untouched.preferences.companions)
        self.assertEqual(untouched.preferences.interest_tags, [])

    async def test_append_turn_persists_turns(self) -> None:
        session_id = str(uuid4())
        await self.manager.append_turn(session_id, build_turn(str(uuid4()), "Plan a day in Taipei"))

        session = await self.manager.get_or_create(session_id)

        self.assertEqual(len(session.turns), 1)
        self.assertEqual(session.turns[0].content, "Plan a day in Taipei")

    async def test_update_preferences_updates_only_intended_fields(self) -> None:
        session_id = str(uuid4())
        await self.manager.update_preferences(
            session_id,
            Preferences(
                companions="solo",
                interest_tags=["cafes"],
                language="en",
            ),
        )
        await self.manager.update_preferences(
            session_id,
            Preferences(budget_level="mid-range"),
        )

        session = await self.manager.get_or_create(session_id)

        self.assertEqual(session.preferences.companions, "solo")
        self.assertEqual(session.preferences.interest_tags, ["cafes"])
        self.assertEqual(session.preferences.budget_level, "mid-range")
        self.assertEqual(session.preferences.language, "en")

    async def test_set_itinerary_and_cache_candidates_persist(self) -> None:
        session_id = str(uuid4())
        itinerary = build_itinerary()
        candidates = [
            Place(venue_id=100, name="Candidate A", category="attraction", lat=25.0, lng=121.5),
            Place(venue_id=101, name="Candidate B", category="food", lat=25.1, lng=121.6),
        ]

        await self.manager.set_itinerary(session_id, itinerary)
        await self.manager.cache_candidates(session_id, candidates)

        session = await self.manager.get_or_create(session_id)

        self.assertIsNotNone(session.latest_itinerary)
        self.assertEqual(session.latest_itinerary.summary, "Two-stop route")
        self.assertEqual([candidate.name for candidate in session.cached_candidates], ["Candidate A", "Candidate B"])

    async def test_invalid_session_id_raises(self) -> None:
        with self.assertRaises(InvalidSessionIdError):
            await self.manager.get_or_create("not-a-uuid")

    async def test_concurrent_appends_are_safe(self) -> None:
        session_id = str(uuid4())
        turn_ids = [str(uuid4()) for _ in range(25)]

        await asyncio.gather(
            *(
                self.manager.append_turn(session_id, build_turn(turn_id, f"message-{index}"))
                for index, turn_id in enumerate(turn_ids)
            )
        )

        session = await self.manager.get_or_create(session_id)
        stored_turn_ids = [turn.turn_id for turn in session.turns]

        self.assertEqual(len(session.turns), 25)
        self.assertCountEqual(stored_turn_ids, turn_ids)
