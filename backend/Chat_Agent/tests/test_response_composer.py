from __future__ import annotations

import unittest

from app.chat.response_composer import ResponseComposer
from app.session.models import Preferences
from app.tools.models import ToolPlace


def build_place(venue_id: int, name: str) -> ToolPlace:
    return ToolPlace(
        venue_id=venue_id,
        name=name,
        district="中山區",
        category="food",
        primary_type="ramen_restaurant",
        rating=4.6,
        budget_level="mid",
        lat=25.05,
        lng=121.52,
    )


class ResponseComposerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.composer = ResponseComposer()
        self.places = [
            build_place(1, "Ramen One"),
            build_place(2, "Ramen Two"),
            build_place(3, "Ramen Three"),
        ]

    def test_relaxation_message_zh_tw(self) -> None:
        reply, candidates = self.composer.compose_recommendation_with_relaxation(
            places=self.places,
            preferences=Preferences(language="zh-TW"),
            relaxations=["dropped_district"],
            original_filters={
                "district": "北投區",
                "primary_type": "ramen_restaurant",
            },
        )

        self.assertEqual(len(candidates), 3)
        self.assertIn("擴大到整個台北", reply)
        self.assertIn("Ramen One", reply)
        self.assertIn("Ramen Two", reply)
        self.assertIn("Ramen Three", reply)

    def test_relaxation_message_en(self) -> None:
        reply, candidates = self.composer.compose_recommendation_with_relaxation(
            places=self.places,
            preferences=Preferences(language="en"),
            relaxations=["dropped_district"],
            original_filters={
                "district": "Beitou District",
                "primary_type": "ramen_restaurant",
            },
        )

        self.assertEqual(len(candidates), 3)
        self.assertIn("broadened the search beyond the original district", reply)
        self.assertIn("Ramen One", reply)
        self.assertIn("Ramen Two", reply)
        self.assertIn("Ramen Three", reply)
