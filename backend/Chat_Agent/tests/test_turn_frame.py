from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.orchestration.intents import Intent
from app.orchestration.turn_frame import (
    PlaceConstraint,
    TargetReference,
    TurnIntentFrame,
    VibeTagSelection,
    extract_replan_turn_frame,
    select_known_vibe_tags,
    stable_preference_delta_for_merge,
    validate_turn_intent_frame,
)
from app.session.models import Itinerary, Leg, Preferences, Stop
from tests.fake_llm import DisabledLLMClient, StaticJSONClient


def build_itinerary() -> Itinerary:
    stops = [
        Stop(
            stop_index=0,
            venue_id=1,
            venue_name="Cafe A",
            category="food",
            arrival_time="10:00",
            visit_duration_min=60,
        ),
        Stop(
            stop_index=1,
            venue_id=2,
            venue_name="Cafe B",
            category="food",
            arrival_time="11:10",
            visit_duration_min=60,
        ),
        Stop(
            stop_index=2,
            venue_id=3,
            venue_name="Cafe C",
            category="food",
            arrival_time="12:20",
            visit_duration_min=60,
        ),
    ]
    legs = [
        Leg(from_stop=0, to_stop=1, transit_method="transit", duration_min=10, estimated=False),
        Leg(from_stop=1, to_stop=2, transit_method="transit", duration_min=10, estimated=False),
    ]
    return Itinerary(summary="test", total_duration_min=200, stops=stops, legs=legs)


class TurnIntentFrameValidationTests(unittest.TestCase):
    def test_valid_replan_frame_is_accepted(self) -> None:
        frame = TurnIntentFrame(
            intent=Intent.REPLAN,
            source="regex",
            confidence=0.95,
            operation="replace",
            target_reference=TargetReference(
                kind="ordinal",
                raw_text="第二站",
                resolved_index=1,
                confidence=1.0,
            ),
            replacement_constraint=PlaceConstraint(internal_category="attraction"),
            raw_user_message="第二站換成景點",
        )

        self.assertEqual(frame.operation, "replace")
        self.assertEqual(frame.target_reference.resolved_index, 1)

    def test_replan_frame_requires_operation(self) -> None:
        with self.assertRaises(ValidationError):
            TurnIntentFrame(
                intent=Intent.REPLAN,
                source="regex",
                confidence=0.9,
                raw_user_message="幫我改一下行程",
            )

    def test_replan_frame_requires_target_reference_when_not_clarifying(self) -> None:
        with self.assertRaises(ValidationError):
            TurnIntentFrame(
                intent=Intent.REPLAN,
                source="regex",
                confidence=0.9,
                operation="replace",
                raw_user_message="換成景點",
            )

    def test_validate_turn_frame_marks_out_of_range_target_for_clarification(self) -> None:
        frame = TurnIntentFrame(
            intent=Intent.REPLAN,
            source="llm",
            confidence=0.85,
            operation="replace",
            target_reference=TargetReference(
                kind="index",
                raw_text="第四站",
                resolved_index=3,
                confidence=0.85,
            ),
            raw_user_message="第四站換成公園",
            needs_clarification=True,
        )

        validated = validate_turn_intent_frame(frame, itinerary=build_itinerary())

        self.assertTrue(validated.needs_clarification)
        self.assertIn("target_reference", validated.missing_fields)

    def test_stable_preference_delta_for_merge_drops_turn_only_fields(self) -> None:
        frame = TurnIntentFrame(
            intent=Intent.CHAT_GENERAL,
            source="llm",
            confidence=0.8,
            stable_preference_delta=Preferences(
                district="信義區",
                language="zh-TW",
                interest_tags=["nature"],
                avoid_tags=["crowded"],
            ),
            raw_user_message="之後都用中文，從信義區出發",
        )

        stable_delta = stable_preference_delta_for_merge(frame)

        self.assertIsNotNone(stable_delta)
        assert stable_delta is not None
        self.assertEqual(stable_delta.district, "信義區")
        self.assertEqual(stable_delta.language, "zh-TW")
        self.assertNotIn("interest_tags", stable_delta.model_fields_set)
        self.assertNotIn("avoid_tags", stable_delta.model_fields_set)

    def test_unknown_selected_vibe_tags_are_rejected_and_recorded(self) -> None:
        frame = TurnIntentFrame(
            intent=Intent.CHAT_GENERAL,
            source="llm",
            confidence=0.8,
            search_constraint=PlaceConstraint(vibe_tags=["romantic", "quiet"]),
            vibe_tag_selection=VibeTagSelection(
                selected_tags=["romantic", "quiet"],
                rejected_tags=[],
                confidence=0.9,
                fallback_strategy="none",
            ),
            raw_user_message="想找浪漫安靜的餐廳",
        )

        validated = validate_turn_intent_frame(
            frame,
            known_vibe_tags=["romantic", "scenic"],
        )

        self.assertEqual(validated.search_constraint.vibe_tags, ["romantic"])
        self.assertEqual(validated.vibe_tag_selection.selected_tags, ["romantic"])
        self.assertIn("quiet", validated.vibe_tag_selection.rejected_tags)


class TurnIntentFrameExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_replan_turn_frame_fast_path_for_second_one_attraction(self) -> None:
        frame = await extract_replan_turn_frame(
            "可以把第二個換成景點嗎",
            build_itinerary(),
            client=DisabledLLMClient(),
        )

        self.assertEqual(frame.source, "regex")
        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.operation, "replace")
        self.assertEqual(frame.target_reference.resolved_index, 1)
        self.assertEqual(frame.replacement_constraint.internal_category, "attraction")

    async def test_extract_replan_turn_frame_fast_path_for_park(self) -> None:
        frame = await extract_replan_turn_frame(
            "第三站換成公園",
            build_itinerary(),
            client=DisabledLLMClient(),
        )

        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.target_reference.resolved_index, 2)
        self.assertEqual(frame.replacement_constraint.internal_category, "attraction")
        self.assertEqual(frame.replacement_constraint.primary_type, "park")

    async def test_extract_replan_turn_frame_fast_path_for_japanese_restaurant(self) -> None:
        frame = await extract_replan_turn_frame(
            "第一站換成日式餐廳",
            build_itinerary(),
            client=DisabledLLMClient(),
        )

        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.target_reference.resolved_index, 0)
        self.assertEqual(frame.replacement_constraint.internal_category, "food")
        self.assertEqual(frame.replacement_constraint.primary_type, "japanese_restaurant")

    async def test_extract_replan_turn_frame_fast_path_for_remove_variant(self) -> None:
        frame = await extract_replan_turn_frame(
            "把第二站移掉",
            build_itinerary(),
            client=DisabledLLMClient(),
        )

        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.operation, "remove")
        self.assertEqual(frame.target_reference.resolved_index, 1)

    async def test_extract_replan_turn_frame_supports_last_stop_in_english(self) -> None:
        frame = await extract_replan_turn_frame(
            "replace the last stop with a park",
            build_itinerary(),
            client=DisabledLLMClient(),
        )

        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.target_reference.resolved_index, 2)
        self.assertEqual(frame.target_reference.kind, "relative")

    async def test_extract_replan_turn_frame_ambiguous_target_needs_clarification(self) -> None:
        frame = await extract_replan_turn_frame(
            "換成景點",
            build_itinerary(),
            client=DisabledLLMClient(),
        )

        self.assertTrue(frame.needs_clarification)
        self.assertIn("target_reference", frame.missing_fields)

    async def test_extract_replan_turn_frame_uses_llm_for_named_stop_reference(self) -> None:
        client = StaticJSONClient(
            {
                "intent": "REPLAN",
                "source": "llm",
                "confidence": 0.88,
                "needs_clarification": False,
                "missing_fields": [],
                "operation": "replace",
                "target_reference": {
                    "kind": "name",
                    "raw_text": "Cafe B",
                    "resolved_index": 1,
                    "confidence": 0.88,
                },
                "replacement_constraint": {
                    "internal_category": "food",
                    "keyword": "coffee",
                },
            }
        )

        frame = await extract_replan_turn_frame(
            "把 Cafe B 換成咖啡廳",
            build_itinerary(),
            client=client,
        )

        self.assertEqual(frame.source, "hybrid")
        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.target_reference.kind, "name")
        self.assertEqual(frame.target_reference.resolved_index, 1)
        self.assertEqual(frame.replacement_constraint.keyword, "coffee")

    async def test_extract_replan_turn_frame_accepts_legacy_replace_payload(self) -> None:
        frame = await extract_replan_turn_frame(
            "把 Cafe B 改一下",
            build_itinerary(),
            client=StaticJSONClient(
                {
                    "operation": "replace",
                    "target_index": 2,
                    "insert_index": None,
                    "needs_clarification": False,
                    "missing_fields": [],
                }
            ),
        )

        self.assertEqual(frame.source, "hybrid")
        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.operation, "replace")
        self.assertEqual(frame.target_reference.kind, "index")
        self.assertEqual(frame.target_reference.resolved_index, 2)

    async def test_extract_replan_turn_frame_accepts_legacy_insert_payload(self) -> None:
        frame = await extract_replan_turn_frame(
            "幫我加一站",
            build_itinerary(),
            client=StaticJSONClient(
                {
                    "operation": "insert",
                    "target_index": None,
                    "insert_index": 1,
                    "needs_clarification": False,
                    "missing_fields": [],
                }
            ),
        )

        self.assertEqual(frame.source, "hybrid")
        self.assertFalse(frame.needs_clarification)
        self.assertEqual(frame.operation, "insert")
        self.assertEqual(frame.target_reference.kind, "index")
        self.assertEqual(frame.target_reference.resolved_index, 0)

    async def test_select_known_vibe_tags_keeps_romantic_when_catalog_contains_it(self) -> None:
        selection = await select_known_vibe_tags(
            "幫我找一間日式餐廳浪漫一點的",
            ["romantic", "scenic"],
            client=StaticJSONClient(
                {
                    "selected_tags": ["romantic"],
                    "rejected_tags": [],
                    "confidence": 0.92,
                    "fallback_strategy": "none",
                }
            ),
        )

        self.assertEqual(selection.selected_tags, ["romantic"])
        self.assertEqual(selection.rejected_tags, [])
        self.assertEqual(selection.fallback_strategy, "none")

    async def test_select_known_vibe_tags_rejects_romantic_when_catalog_missing_it(self) -> None:
        selection = await select_known_vibe_tags(
            "幫我找一間日式餐廳浪漫一點的",
            ["scenic"],
            client=StaticJSONClient(
                {
                    "selected_tags": ["romantic"],
                    "rejected_tags": [],
                    "confidence": 0.92,
                    "fallback_strategy": "none",
                }
            ),
        )

        self.assertEqual(selection.selected_tags, [])
        self.assertIn("romantic", selection.rejected_tags)
        self.assertEqual(selection.fallback_strategy, "broaden_search")

    async def test_select_known_vibe_tags_with_empty_catalog_returns_broaden_search(self) -> None:
        selection = await select_known_vibe_tags(
            "romantic restaurant",
            [],
            client=DisabledLLMClient(),
        )

        self.assertEqual(selection.selected_tags, [])
        self.assertEqual(selection.rejected_tags, [])
        self.assertEqual(selection.fallback_strategy, "broaden_search")
