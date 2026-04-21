from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from app.orchestration.classifier import IntentClassifier, RuleBasedClassifier
from app.orchestration.intents import Intent
from app.orchestration.slots import GenerateItinerarySlots, ReplanSlots


class IntentClassifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_deterministic_classifier_identifies_generate_itinerary(self) -> None:
        classifier = IntentClassifier()

        result = await classifier.classify("幫我排今晚從台北車站出發的半日約會行程")

        self.assertEqual(result.intent, Intent.GENERATE_ITINERARY)
        self.assertFalse(result.needs_clarification)
        self.assertIsInstance(result.extracted_slots, GenerateItinerarySlots)
        self.assertEqual(result.extracted_slots.origin, "台北車站")

    async def test_deterministic_classifier_identifies_replan(self) -> None:
        classifier = IntentClassifier()

        result = await classifier.classify("請換掉第二站，改成寺廟")

        self.assertEqual(result.intent, Intent.REPLAN)
        self.assertIsInstance(result.extracted_slots, ReplanSlots)
        self.assertEqual(result.extracted_slots.stop_index, 1)

    async def test_deterministic_classifier_identifies_explain(self) -> None:
        classifier = IntentClassifier()

        result = await classifier.classify("Why did you pick this route?", has_itinerary=True)

        self.assertEqual(result.intent, Intent.EXPLAIN)
        self.assertGreaterEqual(result.confidence, 0.88)

    async def test_vague_itinerary_request_needs_clarification(self) -> None:
        classifier = IntentClassifier()

        result = await classifier.classify("幫我排一下行程")

        self.assertEqual(result.intent, Intent.GENERATE_ITINERARY)
        self.assertTrue(result.needs_clarification)
        self.assertIn("origin", result.missing_fields)

    async def test_low_confidence_path_uses_llm_fallback(self) -> None:
        classifier = IntentClassifier()
        classifier._client.generate_json = AsyncMock(
            return_value={
                "intent": "EXPLAIN",
                "confidence": 0.87,
                "needs_clarification": False,
                "extracted_slots": {"subject": "Longshan Temple"},
                "missing_fields": [],
            }
        )

        result = await classifier.classify("Can you elaborate on that choice?")

        self.assertEqual(result.intent, Intent.EXPLAIN)
        self.assertEqual(result.source, "llm")
        classifier._client.generate_json.assert_awaited_once()

    def test_phase3_modules_do_not_depend_on_tools_package(self) -> None:
        from pathlib import Path

        classifier_source = Path("app/orchestration/classifier.py").read_text(encoding="utf-8")
        preferences_source = Path("app/orchestration/preferences.py").read_text(encoding="utf-8")

        self.assertNotIn("app.tools", classifier_source)
        self.assertNotIn("app.tools", preferences_source)


class RuleBasedClassifierTests(unittest.TestCase):
    def test_rule_based_classifier_falls_back_to_chat_general_for_ambiguous_input(self) -> None:
        classifier = RuleBasedClassifier()

        result = classifier.classify("Tell me something fun in Taipei")

        self.assertEqual(result.intent, Intent.CHAT_GENERAL)
        self.assertLess(result.confidence, 0.8)
