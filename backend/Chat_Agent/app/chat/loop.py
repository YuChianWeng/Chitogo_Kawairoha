from __future__ import annotations

import re
from typing import Any

from app.chat.schemas import ChatUserContext, LoopResult
from app.core.config import Settings, get_settings
from app.orchestration.intents import Intent
from app.session.models import Preferences
from app.tools.models import PlaceListResult, ToolPlace
from app.tools.registry import ToolRegistry, tool_registry

_DISCOVERY_PATTERN = re.compile(
    r"(推薦|想找|找一下|找個|附近|有沒有|去哪|吃什麼|recommend|suggest|looking for|search|nearby|where should|what should)",
    re.IGNORECASE,
)
_SEARCH_PATTERN = re.compile(
    r"(找|search|looking for|想找|想吃|哪裡有|where can i find)",
    re.IGNORECASE,
)
_NEARBY_PATTERN = re.compile(r"(附近|nearby|near me|close by)", re.IGNORECASE)

_INTEREST_TO_CATEGORY = {
    "cafes": "food",
    "food": "food",
    "night-market": "nightlife",
    "shopping": "shopping",
    "museums": "attraction",
    "temples": "attraction",
    "nature": "attraction",
}
_INTEREST_TO_KEYWORD = {
    "cafes": "cafe",
    "food": "restaurant",
    "night-market": "night market",
    "shopping": "shopping",
    "museums": "museum",
    "temples": "temple",
    "nature": "park",
}
_BUDGET_TO_MAX_LEVEL = {
    "budget": 1,
    "mid": 2,
    "luxury": 4,
}


class AgentLoop:
    """Minimal, deterministic recommendation orchestration for Phase 5."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._registry = registry or tool_registry
        self._settings = settings

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @staticmethod
    def is_discovery_message(message: str) -> bool:
        return bool(_DISCOVERY_PATTERN.search(message))

    async def run(
        self,
        *,
        intent: Intent,
        message: str,
        preferences: Preferences,
        user_context: ChatUserContext | None = None,
    ) -> LoopResult:
        allowed_tools = {tool.name for tool in self._registry.list_tools_for_intent(intent)}
        tools_used: list[str] = []

        if user_context and self._should_use_nearby(message) and "place_nearby" in allowed_tools:
            result = await self._invoke_place_list_tool(
                "place_nearby",
                tools_used,
                lat=user_context.lat,
                lng=user_context.lng,
                radius_m=1500,
                internal_category=self._preferred_category(preferences),
                min_rating=None,
                max_budget_level=self._max_budget_level(preferences),
                limit=5,
            )
            if result.status == "ok":
                return result

        if self._should_use_recommend(message, preferences) and "place_recommend" in allowed_tools:
            result = await self._invoke_place_list_tool(
                "place_recommend",
                tools_used,
                districts=[preferences.district] if preferences.district else None,
                internal_category=self._preferred_category(preferences),
                min_rating=None,
                max_budget_level=self._max_budget_level(preferences),
                indoor=preferences.indoor_preference,
                limit=5,
            )
            if result.status == "ok":
                return result
            if result.status == "error":
                return result

        if "place_search" not in allowed_tools:
            return LoopResult(status="error", tools_used=tools_used, error="tool_unavailable")

        return await self._invoke_place_list_tool(
            "place_search",
            tools_used,
            district=preferences.district,
            internal_category=self._preferred_category(preferences),
            keyword=self._search_keyword(message, preferences),
            min_rating=None,
            max_budget_level=self._max_budget_level(preferences),
            indoor=preferences.indoor_preference,
            limit=5,
            offset=0,
        )

    async def _invoke_place_list_tool(
        self,
        tool_name: str,
        tools_used: list[str],
        **kwargs: Any,
    ) -> LoopResult:
        tool = self._registry.get_tool(tool_name)
        if tool is None:
            return LoopResult(status="error", tools_used=list(tools_used), error="tool_unavailable")
        filtered_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        try:
            raw_result = await tool.handler(**filtered_kwargs)
        except Exception as exc:
            tools_used.append(tool_name)
            return LoopResult(
                status="error",
                tools_used=list(tools_used),
                error=exc.__class__.__name__,
            )
        tools_used.append(tool_name)
        if not isinstance(raw_result, PlaceListResult):
            return LoopResult(status="error", tools_used=list(tools_used), error="malformed_tool_result")
        if raw_result.status == "error":
            return LoopResult(status="error", tools_used=list(tools_used), error=raw_result.error)
        if raw_result.status == "empty":
            return LoopResult(
                status="empty",
                tools_used=list(tools_used),
                places=[],
                summary="no_matches",
            )
        return LoopResult(
            status="ok",
            tools_used=list(tools_used),
            places=list(raw_result.items),
            summary=f"{len(raw_result.items)} candidates",
        )

    @staticmethod
    def _preferred_category(preferences: Preferences) -> str | None:
        for tag in preferences.interest_tags:
            if tag in _INTEREST_TO_CATEGORY:
                return _INTEREST_TO_CATEGORY[tag]
        return None

    @staticmethod
    def _max_budget_level(preferences: Preferences) -> int | None:
        if preferences.budget_level is None:
            return None
        return _BUDGET_TO_MAX_LEVEL.get(preferences.budget_level)

    @staticmethod
    def _search_keyword(message: str, preferences: Preferences) -> str | None:
        for tag in preferences.interest_tags:
            if tag in _INTEREST_TO_KEYWORD:
                return _INTEREST_TO_KEYWORD[tag]
        if _SEARCH_PATTERN.search(message):
            cleaned = message.strip()
            return cleaned if len(cleaned) <= 40 else cleaned[:40]
        return None

    @staticmethod
    def _should_use_nearby(message: str) -> bool:
        return bool(_NEARBY_PATTERN.search(message))

    @staticmethod
    def _should_use_recommend(message: str, preferences: Preferences) -> bool:
        if _SEARCH_PATTERN.search(message):
            return False
        return bool(
            preferences.district
            or preferences.origin
            or preferences.interest_tags
            or preferences.budget_level
            or preferences.indoor_preference is not None
        )
