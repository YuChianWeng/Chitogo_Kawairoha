from __future__ import annotations

import logging
import re

from app.llm.client import LLMClient, llm_client
from app.orchestration.intents import Intent
from app.orchestration.slots import (
    ChatGeneralSlots,
    ClassifierResult,
    GenerateItinerarySlots,
    slot_model_for_intent,
)
from app.session.models import Preferences

_TIME_HINT_PATTERN = re.compile(
    r"(\d{1,2}:\d{2}|今晚|今天|明天|下午|早上|晚上|tonight|tomorrow|morning|afternoon|evening)",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


def _normalize_slots_for_intent(intent: Intent, raw_slots: dict[str, object]) -> dict[str, object]:
    slot_model = slot_model_for_intent(intent)
    normalized = {
        field_name: raw_slots[field_name]
        for field_name in slot_model.model_fields
        if field_name in raw_slots
    }
    if intent == Intent.GENERATE_ITINERARY:
        normalized = _coerce_generate_slots(normalized)
    return normalized


def _coerce_generate_slots(raw_slots: dict[str, object]) -> dict[str, object]:
    normalized = dict(raw_slots)
    scalar_fields = {"origin", "district", "companions", "budget_level", "transport_mode"}
    list_fields = {"interest_tags", "avoid_tags"}

    for field_name in scalar_fields:
        value = normalized.get(field_name)
        if isinstance(value, list):
            normalized[field_name] = next(
                (item.strip() for item in value if isinstance(item, str) and item.strip()),
                None,
            )

    for field_name in list_fields:
        value = normalized.get(field_name)
        if value is None:
            normalized[field_name] = []
            continue
        if isinstance(value, str):
            normalized[field_name] = [value]

    return normalized


def _detect_missing_generate_info(message: str, slots: GenerateItinerarySlots) -> list[str]:
    missing_fields: list[str] = []
    has_origin = bool(slots.origin)
    has_time = bool(slots.time_window) or bool(_TIME_HINT_PATTERN.search(message))
    has_context = any(
        [
            slots.companions,
            slots.district,
            slots.budget_level,
            slots.transport_mode,
            slots.interest_tags,
            slots.avoid_tags,
        ]
    )

    if not has_origin:
        missing_fields.append("origin")
    if not has_time:
        missing_fields.append("time_window")
    if not has_context:
        missing_fields.append("context")
    return missing_fields if len(missing_fields) >= 2 else []


def detect_missing_generate_fields(
    message: str,
    preferences: Preferences,
) -> list[str]:
    return _detect_missing_generate_info(
        message,
        GenerateItinerarySlots(
            origin=preferences.origin,
            district=preferences.district,
            time_window=preferences.time_window,
            companions=preferences.companions,
            budget_level=preferences.budget_level,
            transport_mode=preferences.transport_mode,
            interest_tags=list(preferences.interest_tags),
            avoid_tags=list(preferences.avoid_tags),
        ),
    )


def build_classifier_prompt(message: str, has_itinerary: bool) -> str:
    return (
        "Classify the latest user message for a Taipei travel assistant.\n"
        "Valid intents:\n"
        "- GENERATE_ITINERARY: user wants to plan or schedule a trip itinerary\n"
        "- REPLAN: user wants to modify an existing itinerary (replace, insert, or remove stops)\n"
        "- EXPLAIN: user is asking why certain places were chosen\n"
        "- CHAT_GENERAL: anything else\n"
        "Return strict JSON with exactly these keys: intent, confidence, needs_clarification, "
        "missing_fields, extracted_slots.\n"
        "confidence must be a float from 0.0 to 1.0.\n"
        "missing_fields must be an array of strings.\n"
        "extracted_slots must match the detected intent:\n"
        "- GENERATE_ITINERARY: {origin, district, time_window, companions, budget_level, transport_mode, interest_tags, avoid_tags}\n"
        "- REPLAN: {stop_index, change_request}\n"
        "- EXPLAIN: {subject}\n"
        "- CHAT_GENERAL: {topic}\n"
        "Use stop_index as zero-based when present.\n"
        "time_window MUST be {\"start_time\": \"HH:MM\", \"end_time\": \"HH:MM\"} or null. "
        "Never use a plain string. Convert relative expressions: '下午' → {\"start_time\": \"13:00\", \"end_time\": \"18:00\"}, "
        "'今晚' → {\"start_time\": \"18:00\", \"end_time\": \"22:00\"}, "
        "'早上' → {\"start_time\": \"09:00\", \"end_time\": \"12:00\"}.\n"
        "Return JSON only, without markdown.\n"
        f"has_current_itinerary: {has_itinerary}\n"
        f"message: {message}"
    )


class IntentClassifier:
    """LLM-first classifier with safe fallback behavior."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client = client or llm_client

    async def classify(self, message: str, has_itinerary: bool = False) -> ClassifierResult:
        llm_result = await self._classify_with_llm(message, has_itinerary=has_itinerary)
        if llm_result is not None:
            return llm_result
        return ClassifierResult(
            intent=Intent.CHAT_GENERAL,
            confidence=0.0,
            extracted_slots=ChatGeneralSlots(topic=message.strip() or None),
            source="rules",
        )

    async def _classify_with_llm(
        self,
        message: str,
        *,
        has_itinerary: bool,
    ) -> ClassifierResult | None:
        try:
            payload = await self._client.generate_json(build_classifier_prompt(message, has_itinerary))
        except Exception:
            logger.warning("classifier LLM error", exc_info=True)
            return None

        try:
            if not isinstance(payload, dict):
                return None
            intent = Intent(payload["intent"])
            raw_slots = payload["extracted_slots"]
            if not isinstance(raw_slots, dict):
                return None
            missing_fields = payload["missing_fields"]
            if not isinstance(missing_fields, list):
                return None

            slot_model = slot_model_for_intent(intent)
            raw_slots = _normalize_slots_for_intent(intent, raw_slots)
            result = ClassifierResult(
                intent=intent,
                confidence=float(payload["confidence"]),
                needs_clarification=bool(payload["needs_clarification"]),
                extracted_slots=slot_model.model_validate(raw_slots),
                missing_fields=[str(item) for item in missing_fields],
                source="llm",
            )
        except Exception:
            logger.warning("classifier LLM parse error", exc_info=True)
            return None

        if intent == Intent.GENERATE_ITINERARY and isinstance(result.extracted_slots, GenerateItinerarySlots):
            if not result.missing_fields:
                result.missing_fields = _detect_missing_generate_info(message, result.extracted_slots)
            result.needs_clarification = result.needs_clarification or bool(result.missing_fields)
        return result


__all__ = [
    "IntentClassifier",
    "build_classifier_prompt",
    "detect_missing_generate_fields",
]
