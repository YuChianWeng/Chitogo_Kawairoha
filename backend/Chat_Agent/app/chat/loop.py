from __future__ import annotations

from contextlib import nullcontext
import logging
import re
from typing import TYPE_CHECKING
from typing import Any

from app.chat.prompt_builder import summarize_preferences
from app.chat.schemas import ChatUserContext, LoopResult
from app.core.config import Settings, get_settings
from app.llm.client import llm_client
from app.orchestration.intents import Intent
from app.orchestration.preferences import _VALID_DISTRICTS
from app.session.models import Preferences
from app.tools.models import PlaceListResult, ToolPlace
from app.tools.registry import ToolRegistry, tool_registry

if TYPE_CHECKING:
    from app.chat.trace_recorder import TraceRecorder

logger = logging.getLogger(__name__)

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
_PLANNABLE_TOOL_NAMES = frozenset({"place_search", "place_recommend", "place_nearby"})
_VALID_INTERNAL_CATEGORIES = frozenset({"food", "attraction", "shopping", "nightlife", "lodging"})


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
        self._client = llm_client

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
        trace_recorder: TraceRecorder | None = None,
    ) -> LoopResult:
        tool_definitions = self._registry.list_tools_for_intent(intent)
        allowed_tools = {tool.name for tool in tool_definitions}
        planning_tools = [tool for tool in tool_definitions if tool.name in _PLANNABLE_TOOL_NAMES]
        tools_used: list[str] = []

        planned_call = await self._plan_tool_call(message, preferences, planning_tools)
        if planned_call is not None:
            planned_result = await self._run_planned_call(
                tool_name=planned_call["tool"],
                params=planned_call["params"],
                message=message,
                preferences=preferences,
                user_context=user_context,
                trace_recorder=trace_recorder,
                allowed_tools=allowed_tools,
                tools_used=tools_used,
            )
            if planned_result is not None:
                return planned_result

        return await self._run_deterministic_chain(
            message=message,
            preferences=preferences,
            user_context=user_context,
            trace_recorder=trace_recorder,
            allowed_tools=allowed_tools,
            tools_used=tools_used,
        )

    async def _run_deterministic_chain(
        self,
        *,
        message: str,
        preferences: Preferences,
        user_context: ChatUserContext | None,
        trace_recorder: TraceRecorder | None,
        allowed_tools: set[str],
        tools_used: list[str],
    ) -> LoopResult:
        if (
            user_context
            and user_context.lat is not None
            and user_context.lng is not None
            and self._should_use_nearby(message)
            and "place_nearby" in allowed_tools
        ):
            result = await self._invoke_place_list_tool(
                "place_nearby",
                tools_used,
                trace_recorder=trace_recorder,
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
                trace_recorder=trace_recorder,
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
            trace_recorder=trace_recorder,
            district=preferences.district,
            internal_category=self._preferred_category(preferences),
            keyword=self._search_keyword(message, preferences),
            min_rating=None,
            max_budget_level=self._max_budget_level(preferences),
            indoor=preferences.indoor_preference,
            limit=5,
            offset=0,
        )

    async def _plan_tool_call(
        self,
        message: str,
        preferences: Preferences,
        allowed_tools: list[Any],
    ) -> dict[str, Any] | None:
        if not allowed_tools:
            return None

        tool_lines = "\n".join(
            f"- {tool.name}: {tool.description}"
            for tool in allowed_tools
        )
        allowed_tool_names = ", ".join(tool.name for tool in allowed_tools)
        prompt = (
            "Choose the single best place-discovery tool for the latest user message.\n"
            f"User message: {message}\n"
            f"Current preferences summary: {summarize_preferences(preferences)}\n"
            "Allowed tools:\n"
            f"{tool_lines}\n"
            "Return strict JSON with keys: tool, params.\n"
            f"tool must be one of: {allowed_tool_names}.\n"
            "params must be an object.\n"
            'For place_search/place_nearby/place_recommend, params may include: district, internal_category, keyword, limit.\n'
            'internal_category must be one of: food, attraction, shopping, nightlife, lodging.\n'
            "limit should be an integer and defaults to 5.\n"
            "Return JSON only, without markdown."
        )
        try:
            payload = await self._client.generate_json(prompt)
        except Exception:
            logger.warning("agent loop plan error", exc_info=True)
            return None
        return self._normalize_planned_call(payload, {tool.name for tool in allowed_tools})

    async def _run_planned_call(
        self,
        *,
        tool_name: str,
        params: dict[str, Any],
        message: str,
        preferences: Preferences,
        user_context: ChatUserContext | None,
        trace_recorder: TraceRecorder | None,
        allowed_tools: set[str],
        tools_used: list[str],
    ) -> LoopResult | None:
        if tool_name not in allowed_tools:
            return None

        limit = params.get("limit", 5)
        district = params.get("district") or preferences.district
        preferred_category = self._preferred_category(preferences)
        preferred_keyword = self._preferred_tag_keyword(preferences)
        internal_category = preferred_category or params.get("internal_category")
        keyword = preferred_keyword or params.get("keyword")

        if tool_name == "place_nearby":
            if user_context is None or user_context.lat is None or user_context.lng is None:
                return None
            return await self._invoke_place_list_tool(
                tool_name,
                tools_used,
                trace_recorder=trace_recorder,
                lat=user_context.lat,
                lng=user_context.lng,
                radius_m=1500,
                internal_category=internal_category,
                min_rating=None,
                max_budget_level=self._max_budget_level(preferences),
                limit=limit,
            )

        if tool_name == "place_recommend":
            return await self._invoke_place_list_tool(
                tool_name,
                tools_used,
                trace_recorder=trace_recorder,
                districts=[district] if district else None,
                internal_category=internal_category,
                min_rating=None,
                max_budget_level=self._max_budget_level(preferences),
                indoor=preferences.indoor_preference,
                limit=limit,
            )

        if tool_name == "place_search":
            result = await self._invoke_place_list_tool(
                tool_name,
                tools_used,
                trace_recorder=trace_recorder,
                district=district,
                internal_category=internal_category,
                keyword=keyword,
                min_rating=None,
                max_budget_level=self._max_budget_level(preferences),
                indoor=preferences.indoor_preference,
                limit=limit,
                offset=0,
            )
            if result.status != "empty" or "place_recommend" not in allowed_tools:
                return result
            return await self._invoke_place_list_tool(
                "place_recommend",
                tools_used,
                trace_recorder=trace_recorder,
                districts=[district] if district else None,
                internal_category=internal_category,
                min_rating=None,
                max_budget_level=self._max_budget_level(preferences),
                indoor=preferences.indoor_preference,
                limit=limit,
            )
        return None

    async def _invoke_place_list_tool(
        self,
        tool_name: str,
        tools_used: list[str],
        trace_recorder: TraceRecorder | None = None,
        **kwargs: Any,
    ) -> LoopResult:
        step_context = (
            trace_recorder.step(f"tool.{tool_name}") if trace_recorder is not None else nullcontext()
        )
        with step_context as trace_step:
            tool = self._registry.get_tool(tool_name)
            if tool is None:
                if trace_step is not None:
                    trace_step.skip(summary="tool_unavailable")
                return LoopResult(
                    status="error",
                    tools_used=list(tools_used),
                    error="tool_unavailable",
                )
            filtered_kwargs = {key: value for key, value in kwargs.items() if value is not None}
            try:
                raw_result = await tool.handler(**filtered_kwargs)
            except Exception as exc:
                tools_used.append(tool_name)
                if trace_step is not None:
                    trace_step.error(
                        summary="tool_exception",
                        error=exc.__class__.__name__,
                    )
                return LoopResult(
                    status="error",
                    tools_used=list(tools_used),
                    error=exc.__class__.__name__,
                )
            tools_used.append(tool_name)
            if not isinstance(raw_result, PlaceListResult):
                if trace_step is not None:
                    trace_step.error(summary="malformed_tool_result")
                return LoopResult(
                    status="error",
                    tools_used=list(tools_used),
                    error="malformed_tool_result",
                )
            if raw_result.status == "error":
                if trace_step is not None:
                    trace_step.error(
                        summary=raw_result.error or "tool_error",
                        detail={"item_count": len(raw_result.items)},
                    )
                return LoopResult(status="error", tools_used=list(tools_used), error=raw_result.error)
            if raw_result.status == "empty":
                if trace_step is not None:
                    trace_step.success(summary="empty", detail={"item_count": 0})
                return LoopResult(
                    status="empty",
                    tools_used=list(tools_used),
                    places=[],
                    summary="no_matches",
                )
            if trace_step is not None:
                trace_step.success(
                    summary="ok",
                    detail={"item_count": len(raw_result.items)},
                )
            return LoopResult(
                status="ok",
                tools_used=list(tools_used),
                places=list(raw_result.items),
                summary=f"{len(raw_result.items)} candidates",
            )

    @staticmethod
    def _normalize_planned_call(
        payload: object,
        allowed_tools: set[str],
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        tool_name = payload.get("tool")
        params = payload.get("params")
        if not isinstance(tool_name, str) or tool_name not in allowed_tools:
            return None
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return None

        allowed_param_keys = {"district", "internal_category", "keyword", "limit"}
        if any(key not in allowed_param_keys for key in params):
            return None

        normalized: dict[str, Any] = {}
        district = params.get("district")
        if district is not None:
            if not isinstance(district, str) or not district.strip():
                return None
            normalized["district"] = district.strip()
            if normalized["district"] not in _VALID_DISTRICTS:
                del normalized["district"]

        internal_category = params.get("internal_category")
        if internal_category is not None:
            if (
                not isinstance(internal_category, str)
                or internal_category not in _VALID_INTERNAL_CATEGORIES
            ):
                return None
            normalized["internal_category"] = internal_category

        keyword = params.get("keyword")
        if keyword is not None:
            if not isinstance(keyword, str) or not keyword.strip():
                return None
            normalized["keyword"] = keyword.strip()

        limit = params.get("limit", 5)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            return None
        normalized["limit"] = limit
        return {"tool": tool_name, "params": normalized}

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
        preferred_keyword = AgentLoop._preferred_tag_keyword(preferences)
        if preferred_keyword is not None:
            return preferred_keyword
        if _SEARCH_PATTERN.search(message):
            cleaned = message.strip()
            return cleaned if len(cleaned) <= 40 else cleaned[:40]
        return None

    @staticmethod
    def _preferred_tag_keyword(preferences: Preferences) -> str | None:
        for tag in preferences.interest_tags:
            if tag in _INTEREST_TO_KEYWORD:
                return _INTEREST_TO_KEYWORD[tag]
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
