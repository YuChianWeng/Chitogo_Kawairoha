from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    """Supported high-level orchestration intents for planner routing."""

    GENERATE_ITINERARY = "GENERATE_ITINERARY"
    REPLAN = "REPLAN"
    EXPLAIN = "EXPLAIN"
    CHAT_GENERAL = "CHAT_GENERAL"
    CHECK_LODGING_LEGAL = "CHECK_LODGING_LEGAL"


__all__ = ["Intent"]
