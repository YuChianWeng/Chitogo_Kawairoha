from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.intents import Intent
from app.session.models import TimeWindow

_CHINESE_ORDINAL_PATTERN = re.compile(r"第\s*([一二三四五六七八九十兩两\d]+)\s*(?:站|個|家|間)")
_NUMERIC_STOP_PATTERN = re.compile(r"(?:stop\s*#?\s*|#)(\d+)|(\d+)(?:st|nd|rd|th)\s+stop", re.IGNORECASE)
_ENGLISH_ORDINAL_PATTERN = re.compile(
    r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+stop\b",
    re.IGNORECASE,
)

_CHINESE_ORDINAL_MAP = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "兩": 2,
    "两": 2,
}
_ENGLISH_ORDINAL_MAP = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def _parse_chinese_ordinal(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    if token in _CHINESE_ORDINAL_MAP:
        return _CHINESE_ORDINAL_MAP[token]
    if len(token) == 2 and token[0] == "十" and token[1] in _CHINESE_ORDINAL_MAP:
        return 10 + _CHINESE_ORDINAL_MAP[token[1]]
    if len(token) == 2 and token[1] == "十" and token[0] in _CHINESE_ORDINAL_MAP:
        return (_CHINESE_ORDINAL_MAP[token[0]] * 10)
    return None


def extract_stop_index(message: str) -> int | None:
    """Extract a zero-based stop index from replan language."""
    chinese_match = _CHINESE_ORDINAL_PATTERN.search(message)
    if chinese_match:
        ordinal = _parse_chinese_ordinal(chinese_match.group(1))
        if ordinal and ordinal >= 1:
            return ordinal - 1

    numeric_match = _NUMERIC_STOP_PATTERN.search(message)
    if numeric_match:
        for group in numeric_match.groups():
            if group:
                ordinal = int(group)
                if ordinal >= 1:
                    return ordinal - 1

    english_match = _ENGLISH_ORDINAL_PATTERN.search(message)
    if english_match:
        ordinal = _ENGLISH_ORDINAL_MAP[english_match.group(1).lower()]
        return ordinal - 1

    return None


class GenerateItinerarySlots(BaseModel):
    """Lightweight structured hints extracted from a generation request."""

    origin: str | None = None
    district: str | None = None
    time_window: TimeWindow | None = None
    companions: str | None = None
    budget_level: str | None = None
    transport_mode: str | None = None
    interest_tags: list[str] = Field(default_factory=list)
    avoid_tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ReplanSlots(BaseModel):
    """Structured slots for itinerary modification requests."""

    stop_index: int | None = Field(default=None, ge=0)
    change_request: str | None = None

    model_config = ConfigDict(extra="forbid")


class ExplainSlots(BaseModel):
    """Structured slots for explanation requests."""

    subject: str | None = None

    model_config = ConfigDict(extra="forbid")


class ChatGeneralSlots(BaseModel):
    """Structured slots for general chat routing."""

    topic: str | None = None

    model_config = ConfigDict(extra="forbid")


class CheckLodgingLegalSlots(BaseModel):
    """Structured slots for lodging legality check requests."""

    lodging_name: str | None = None
    phone: str | None = None
    district: str | None = None

    model_config = ConfigDict(extra="forbid")


class ClassifierResult(BaseModel):
    """Normalized classifier output for later orchestration phases."""

    intent: Intent
    confidence: float = Field(..., ge=0.0, le=1.0)
    needs_clarification: bool = False
    extracted_slots: (
        GenerateItinerarySlots
        | ReplanSlots
        | ExplainSlots
        | CheckLodgingLegalSlots
        | ChatGeneralSlots
        | None
    ) = None
    missing_fields: list[str] = Field(default_factory=list)
    source: Literal["rules", "llm"] = "rules"

    model_config = ConfigDict(extra="forbid")


def slot_model_for_intent(intent: Intent):
    if intent == Intent.GENERATE_ITINERARY:
        return GenerateItinerarySlots
    if intent == Intent.REPLAN:
        return ReplanSlots
    if intent == Intent.EXPLAIN:
        return ExplainSlots
    if intent == Intent.CHECK_LODGING_LEGAL:
        return CheckLodgingLegalSlots
    return ChatGeneralSlots


__all__ = [
    "ChatGeneralSlots",
    "CheckLodgingLegalSlots",
    "ClassifierResult",
    "ExplainSlots",
    "GenerateItinerarySlots",
    "ReplanSlots",
    "extract_stop_index",
    "slot_model_for_intent",
]
