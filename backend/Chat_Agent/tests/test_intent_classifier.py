from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from app.orchestration.classifier import IntentClassifier
from app.orchestration.intents import Intent
from app.orchestration.slots import GenerateItinerarySlots, ReplanSlots


class IntentClassifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_classifier_uses_llm_for_generate_itinerary(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(
            return_value={
                "intent": "GENERATE_ITINERARY",
                "confidence": 0.94,
                "needs_clarification": False,
                "missing_fields": [],
                "extracted_slots": {
                    "origin": "台北車站",
                    "district": "萬華區",
                    "time_window": {"start_time": "18:00", "end_time": "23:00"},
                    "companions": "date",
                    "budget_level": "mid",
                    "transport_mode": "transit",
                    "interest_tags": ["cafes"],
                    "avoid_tags": [],
                },
            }
        )

        result = await classifier.classify("幫我排今晚從台北車站出發的萬華區咖啡約會行程")

        self.assertEqual(result.intent, Intent.GENERATE_ITINERARY)
        self.assertFalse(result.needs_clarification)
        self.assertEqual(result.source, "llm")
        self.assertIsInstance(result.extracted_slots, GenerateItinerarySlots)
        self.assertEqual(result.extracted_slots.origin, "台北車站")
        classifier._client.generate_json.assert_awaited_once()

    async def test_classifier_uses_llm_for_replan(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(
            return_value={
                "intent": "REPLAN",
                "confidence": 0.91,
                "needs_clarification": False,
                "missing_fields": [],
                "extracted_slots": {
                    "stop_index": 1,
                    "change_request": "請把第二站換成寺廟",
                },
            }
        )

        result = await classifier.classify("請把第二站換成寺廟")

        self.assertEqual(result.intent, Intent.REPLAN)
        self.assertIsInstance(result.extracted_slots, ReplanSlots)
        self.assertEqual(result.extracted_slots.stop_index, 1)

    async def test_classifier_uses_llm_for_explain(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(
            return_value={
                "intent": "EXPLAIN",
                "confidence": 0.87,
                "needs_clarification": False,
                "missing_fields": [],
                "extracted_slots": {"subject": "Longshan Temple"},
            }
        )

        result = await classifier.classify("Why did you pick this route?", has_itinerary=True)

        self.assertEqual(result.intent, Intent.EXPLAIN)
        self.assertEqual(result.source, "llm")

    async def test_generate_missing_fields_are_post_processed(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(
            return_value={
                "intent": "GENERATE_ITINERARY",
                "confidence": 0.82,
                "needs_clarification": False,
                "missing_fields": [],
                "extracted_slots": {
                    "origin": None,
                    "district": None,
                    "time_window": None,
                    "companions": None,
                    "budget_level": None,
                    "transport_mode": None,
                    "interest_tags": [],
                    "avoid_tags": [],
                },
            }
        )

        result = await classifier.classify("幫我排一下行程")

        self.assertEqual(result.intent, Intent.GENERATE_ITINERARY)
        self.assertTrue(result.needs_clarification)
        self.assertIn("origin", result.missing_fields)
        self.assertIn("time_window", result.missing_fields)

    async def test_generate_itinerary_coerces_single_item_list_slots(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(
            return_value={
                "intent": "GENERATE_ITINERARY",
                "confidence": 0.9,
                "needs_clarification": False,
                "missing_fields": [],
                "extracted_slots": {
                    "origin": "大安區",
                    "district": "大安區",
                    "time_window": {"start_time": "13:00", "end_time": "18:00"},
                    "companions": ["朋友"],
                    "budget_level": ["mid"],
                    "transport_mode": ["transit"],
                    "interest_tags": "cafes",
                    "avoid_tags": [],
                },
            }
        )

        result = await classifier.classify("我想從大安區出發，今天下午帶朋友去咖啡廳逛逛，預算中等")

        self.assertEqual(result.intent, Intent.GENERATE_ITINERARY)
        self.assertEqual(result.source, "llm")
        self.assertIsInstance(result.extracted_slots, GenerateItinerarySlots)
        self.assertEqual(result.extracted_slots.companions, "朋友")
        self.assertEqual(result.extracted_slots.budget_level, "mid")
        self.assertEqual(result.extracted_slots.transport_mode, "transit")
        self.assertEqual(result.extracted_slots.interest_tags, ["cafes"])

    async def test_generate_itinerary_coerces_null_list_slots_to_empty_lists(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(
            return_value={
                "intent": "GENERATE_ITINERARY",
                "confidence": 0.9,
                "needs_clarification": False,
                "missing_fields": [],
                "extracted_slots": {
                    "origin": "大安區",
                    "district": "大安區",
                    "time_window": {"start_time": "13:00", "end_time": "18:00"},
                    "companions": "friends",
                    "budget_level": "mid",
                    "transport_mode": "transit",
                    "interest_tags": None,
                    "avoid_tags": None,
                },
            }
        )

        result = await classifier.classify("我想從大安區出發，今天下午帶朋友去咖啡廳逛逛，預算中等")

        self.assertEqual(result.intent, Intent.GENERATE_ITINERARY)
        self.assertEqual(result.source, "llm")
        self.assertIsInstance(result.extracted_slots, GenerateItinerarySlots)
        self.assertEqual(result.extracted_slots.interest_tags, [])
        self.assertEqual(result.extracted_slots.avoid_tags, [])

    async def test_llm_failure_falls_back_to_chat_general(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(side_effect=RuntimeError("boom"))

        result = await classifier.classify("Tell me something fun in Taipei")

        self.assertEqual(result.intent, Intent.CHAT_GENERAL)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.source, "rules")

    def test_phase3_modules_do_not_depend_on_tools_package(self) -> None:
        from pathlib import Path

        classifier_source = Path("app/orchestration/classifier.py").read_text(encoding="utf-8")
        preferences_source = Path("app/orchestration/preferences.py").read_text(encoding="utf-8")

        self.assertNotIn("app.tools", classifier_source)
        self.assertNotIn("app.tools", preferences_source)
