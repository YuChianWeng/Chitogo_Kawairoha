from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.session.models import Itinerary, Leg, Stop


class SessionModelTests(unittest.TestCase):
    def test_valid_itinerary_shape_passes(self) -> None:
        itinerary = Itinerary(
            summary="Morning route",
            total_duration_min=105,
            stops=[
                Stop(
                    stop_index=0,
                    venue_id=1,
                    venue_name="Taipei 101",
                    category="attraction",
                    arrival_time="10:00",
                    visit_duration_min=60,
                    lat=25.0338,
                    lng=121.5645,
                ),
                Stop(
                    stop_index=1,
                    venue_id=2,
                    venue_name="Elephant Mountain",
                    category="attraction",
                    arrival_time="11:15",
                    visit_duration_min=30,
                    lat=25.0270,
                    lng=121.5705,
                ),
            ],
            legs=[
                Leg(
                    from_stop=0,
                    to_stop=1,
                    transit_method="transit",
                    duration_min=15,
                    estimated=False,
                )
            ],
        )

        self.assertEqual(len(itinerary.stops), 2)
        self.assertEqual(itinerary.legs[0].to_stop, 1)

    def test_stop_rejects_invalid_arrival_time(self) -> None:
        with self.assertRaises(ValidationError) as exc_info:
            Stop(
                stop_index=0,
                venue_id=1,
                venue_name="Invalid Stop",
                arrival_time="9:30",
            )

        self.assertIn("arrival_time", str(exc_info.exception))

    def test_itinerary_rejects_sparse_stop_indexes(self) -> None:
        with self.assertRaises(ValidationError) as exc_info:
            Itinerary(
                stops=[
                    Stop(stop_index=0, venue_id=1, venue_name="A", arrival_time="10:00"),
                    Stop(stop_index=2, venue_id=2, venue_name="B", arrival_time="11:00"),
                ],
                legs=[
                    Leg(
                        from_stop=0,
                        to_stop=1,
                        transit_method="transit",
                        duration_min=10,
                    )
                ],
            )

        self.assertIn("stop_index values must be dense", str(exc_info.exception))

    def test_itinerary_rejects_invalid_leg_reference(self) -> None:
        with self.assertRaises(ValidationError) as exc_info:
            Itinerary(
                stops=[
                    Stop(stop_index=0, venue_id=1, venue_name="A", arrival_time="10:00"),
                    Stop(stop_index=1, venue_id=2, venue_name="B", arrival_time="11:00"),
                ],
                legs=[
                    Leg(
                        from_stop=0,
                        to_stop=2,
                        transit_method="transit",
                        duration_min=10,
                    )
                ],
            )

        self.assertIn("leg references an out-of-range stop index", str(exc_info.exception))
