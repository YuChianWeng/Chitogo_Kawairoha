from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from app.orchestration.preferences import PreferenceExtractor, combine_preference_deltas
from app.session.manager import merge_preferences
from app.session.models import Preferences


class PreferenceExtractorTests(unittest.IsolatedAsyncioTestCase):
    async def test_preference_extraction_merge_preserves_unrelated_fields(self) -> None:
        extractor = PreferenceExtractor()
        extractor._client.generate_json = AsyncMock(
            return_value={
                "companions": "friends",
                "interest_tags": ["cafes"],
            }
        )
        current = Preferences(
            budget_level="mid",
            transport_mode="transit",
            interest_tags=["museums"],
        )

        delta = await extractor.extract("和朋友去咖啡廳逛逛", current)
        merged = merge_preferences(current, delta)

        self.assertEqual(merged.budget_level, "mid")
        self.assertEqual(merged.transport_mode, "transit")
        self.assertEqual(merged.companions, "friends")
        self.assertEqual(merged.interest_tags, ["museums", "cafes"])

    async def test_preference_extractor_uses_llm_and_language_hint(self) -> None:
        extractor = PreferenceExtractor()
        extractor._client.generate_json = AsyncMock(
            return_value={
                "origin": "台北101",
                "transport_mode": "transit",
            }
        )

        delta = await extractor.extract("今晚從台北101出發，想搭捷運", Preferences())

        self.assertEqual(delta.origin, "台北101")
        self.assertEqual(delta.transport_mode, "transit")
        self.assertEqual(delta.language, "zh-TW")
        extractor._client.generate_json.assert_awaited_once()


class PreferenceDeltaCombinationTests(unittest.TestCase):
    def test_combine_preference_deltas_adds_list_fields_without_resetting(self) -> None:
        first = Preferences(interest_tags=["cafes"], language="en")
        second = Preferences(interest_tags=["museums"], avoid_tags=["shopping"])

        combined = combine_preference_deltas(first, second)

        self.assertEqual(combined.interest_tags, ["cafes", "museums"])
        self.assertEqual(combined.avoid_tags, ["shopping"])
        self.assertEqual(combined.language, "en")
