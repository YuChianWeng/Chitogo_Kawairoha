from __future__ import annotations

import re
from typing import Any

from app.llm.client import LLMClient, llm_client
from app.orchestration.intents import Intent
from app.orchestration.preferences import extract_preferences_from_text
from app.session.models import Preferences
from app.orchestration.slots import (
    ChatGeneralSlots,
    ClassifierResult,
    ExplainSlots,
    GenerateItinerarySlots,
    ReplanSlots,
    extract_stop_index,
    slot_model_for_intent,
)

_GENERATE_PATTERN = re.compile(
    r"(行程|規劃|安排|排一下|旅遊|半日|一日遊|itinerary|plan|trip|day in|schedule)",
    re.IGNORECASE,
)
_REPLAN_PATTERN = re.compile(
    r"(換掉|改掉|修改|替換|重排|replace|swap|change|modify|replan)",
    re.IGNORECASE,
)
_EXPLAIN_PATTERN = re.compile(
    r"^(?:why|how come|explain|為什麼|怎麼|為何|解釋|說明)",
    re.IGNORECASE,
)
_EXPLAIN_SUBJECT_PATTERN = re.compile(
    r"(?:pick|choose|include|安排|選|挑)\s+(.+?)(?:[?？]|$)",
    re.IGNORECASE,
)
_TIME_HINT_PATTERN = re.compile(r"(\d{1,2}:\d{2}|今晚|今天|明天|下午|早上|晚上|tonight|tomorrow|morning|afternoon|evening)", re.IGNORECASE)


def _generate_slots_from_preferences(message: str) -> GenerateItinerarySlots:
    preference_delta = extract_preferences_from_text(message)
    return GenerateItinerarySlots(
        origin=preference_delta.origin,
        district=preference_delta.district,
        time_window=preference_delta.time_window,
        companions=preference_delta.companions,
        budget_level=preference_delta.budget_level,
        transport_mode=preference_delta.transport_mode,
        interest_tags=list(preference_delta.interest_tags),
        avoid_tags=list(preference_delta.avoid_tags),
    )


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


class RuleBasedClassifier:
    """Fast rules-first classifier for obvious planner intents."""

    def classify(self, message: str, has_itinerary: bool = False) -> ClassifierResult:
        stripped = message.strip()
        if not stripped:
            return ClassifierResult(
                intent=Intent.CHAT_GENERAL,
                confidence=0.4,
                needs_clarification=True,
                extracted_slots=ChatGeneralSlots(topic="empty"),
                source="rules",
            )

        if _EXPLAIN_PATTERN.search(stripped):
            subject_match = _EXPLAIN_SUBJECT_PATTERN.search(stripped)
            return ClassifierResult(
                intent=Intent.EXPLAIN,
                confidence=0.92 if has_itinerary else 0.88,
                extracted_slots=ExplainSlots(
                    subject=subject_match.group(1).strip() if subject_match else None
                ),
                source="rules",
            )

        if _REPLAN_PATTERN.search(stripped):
            stop_index = extract_stop_index(stripped)
            return ClassifierResult(
                intent=Intent.REPLAN,
                confidence=0.93 if stop_index is not None else 0.84,
                needs_clarification=stop_index is None,
                missing_fields=["stop_index"] if stop_index is None else [],
                extracted_slots=ReplanSlots(
                    stop_index=stop_index,
                    change_request=stripped,
                ),
                source="rules",
            )

        if _GENERATE_PATTERN.search(stripped):
            slots = _generate_slots_from_preferences(stripped)
            missing_fields = _detect_missing_generate_info(stripped, slots)
            return ClassifierResult(
                intent=Intent.GENERATE_ITINERARY,
                confidence=0.9,
                needs_clarification=bool(missing_fields),
                missing_fields=missing_fields,
                extracted_slots=slots,
                source="rules",
            )

        return ClassifierResult(
            intent=Intent.CHAT_GENERAL,
            confidence=0.55,
            extracted_slots=ChatGeneralSlots(topic=stripped),
            source="rules",
        )


def build_classifier_prompt(message: str, has_itinerary: bool) -> str:
    return (
        "Classify the latest user message into one intent: "
        "GENERATE_ITINERARY, REPLAN, EXPLAIN, CHAT_GENERAL.\n"
        "Return strict JSON with keys: intent, confidence, needs_clarification, extracted_slots, missing_fields.\n"
        "Use stop_index as zero-based when present.\n"
        f"has_current_itinerary: {has_itinerary}\n"
        f"message: {message}"
    )


class IntentClassifier:
    """Hybrid classifier that uses deterministic rules before LLM fallback."""

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        confidence_threshold: float = 0.8,
        rules: RuleBasedClassifier | None = None,
    ) -> None:
        self._client = client or llm_client
        self._rules = rules or RuleBasedClassifier()
        self._confidence_threshold = confidence_threshold

    async def classify(self, message: str, has_itinerary: bool = False) -> ClassifierResult:
        rule_result = self._rules.classify(message, has_itinerary=has_itinerary)
        if rule_result.confidence >= self._confidence_threshold:
            return rule_result

        llm_result = await self._classify_with_llm(message, has_itinerary=has_itinerary)
        if llm_result is not None:
            return llm_result
        return rule_result

    async def _classify_with_llm(
        self,
        message: str,
        *,
        has_itinerary: bool,
    ) -> ClassifierResult | None:
        try:
            payload = await self._client.generate_json(
                build_classifier_prompt(message, has_itinerary),
                model=self._client.fallback_model,
            )
        except Exception:
            return None

        try:
            intent = Intent(payload["intent"])
            raw_slots = payload.get("extracted_slots") or {}
            slot_model = slot_model_for_intent(intent)
            extracted_slots = slot_model.model_validate(raw_slots) if isinstance(raw_slots, dict) else slot_model()
            missing_fields = payload.get("missing_fields") or []
            result = ClassifierResult(
                intent=intent,
                confidence=float(payload.get("confidence", 0.8)),
                needs_clarification=bool(payload.get("needs_clarification", False)),
                extracted_slots=extracted_slots,
                missing_fields=[str(item) for item in missing_fields],
                source="llm",
            )
        except Exception:
            return None

        if intent == Intent.GENERATE_ITINERARY and isinstance(result.extracted_slots, GenerateItinerarySlots):
            if not result.missing_fields:
                result.missing_fields = _detect_missing_generate_info(message, result.extracted_slots)
            result.needs_clarification = result.needs_clarification or bool(result.missing_fields)
        return result


__all__ = [
    "IntentClassifier",
    "RuleBasedClassifier",
    "build_classifier_prompt",
    "detect_missing_generate_fields",
]
