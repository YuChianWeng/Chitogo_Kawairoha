from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from app.orchestration.preferences import PreferenceExtractor, combine_preference_deltas, _detect_district
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

    async def test_invalid_district_is_cleared(self) -> None:
        extractor = PreferenceExtractor()
        extractor._client.generate_json = AsyncMock(
            return_value={
                "district": "板橋區",
                "language": "zh-TW",
            }
        )

        delta = await extractor.extract("我想去板橋區逛逛", Preferences())

        self.assertIsNone(delta.district)
        self.assertEqual(delta.language, "zh-TW")

    async def test_preference_extractor_normalizes_raw_llm_values(self) -> None:
        extractor = PreferenceExtractor()
        extractor._client.generate_json = AsyncMock(
            return_value={
                "companions": ["朋友"],
                "budget_level": "中等",
                "transport_mode": ["捷運"],
                "interest_tags": ["咖啡廳"],
                "avoid_tags": None,
                "district": None,
                "origin": None,
            }
        )

        delta = await extractor.extract(
            "我想從大安區出發，今天下午帶朋友去咖啡廳逛逛，預算中等",
            Preferences(),
        )

        self.assertEqual(delta.companions, "friends")
        self.assertEqual(delta.budget_level, "mid")
        self.assertEqual(delta.transport_mode, "transit")
        self.assertEqual(delta.interest_tags, ["cafes"])
        self.assertEqual(delta.avoid_tags, [])
        self.assertEqual(delta.district, "大安區")
        self.assertEqual(delta.origin, "大安區")

    async def test_llm_failure_returns_language_only_preferences(self) -> None:
        extractor = PreferenceExtractor()
        extractor._client.generate_json = AsyncMock(side_effect=RuntimeError("boom"))

        delta = await extractor.extract("今晚想去咖啡廳", Preferences())

        self.assertEqual(delta.language, "zh-TW")
        self.assertEqual(delta.model_fields_set, {"language"})


class DistrictDetectionTests(unittest.TestCase):
    def test_valid_district_extracted_from_complex_sentence(self) -> None:
        self.assertEqual(_detect_district("幫我從大安區出發排一個下午的咖啡廳行程"), "大安區")

    def test_valid_district_extracted_from_simple_sentence(self) -> None:
        self.assertEqual(_detect_district("大安區有什麼咖啡廳"), "大安區")

    def test_no_district_when_city_only(self) -> None:
        self.assertIsNone(_detect_district("台北有什麼咖啡廳"))

    def test_valid_district_with_prefix_stripped(self) -> None:
        self.assertEqual(_detect_district("我想在中山區附近走走"), "中山區")

    def test_non_taipei_district_returns_none(self) -> None:
        self.assertIsNone(_detect_district("我想去板橋區逛逛"))


class PreferenceDeltaCombinationTests(unittest.TestCase):
    def test_combine_preference_deltas_adds_list_fields_without_resetting(self) -> None:
        first = Preferences(interest_tags=["cafes"], language="en")
        second = Preferences(interest_tags=["museums"], avoid_tags=["shopping"])

        combined = combine_preference_deltas(first, second)

        self.assertEqual(combined.interest_tags, ["cafes", "museums"])
        self.assertEqual(combined.avoid_tags, ["shopping"])
        self.assertEqual(combined.language, "en")
