from __future__ import annotations

import re
from typing import Any

from app.llm.client import LLMClient, llm_client
from app.orchestration.language import detect_language_hint
from app.session.models import Preferences, TimeWindow

_TIME_RANGE_PATTERN = re.compile(r"(\d{1,2}:\d{2})\s*(?:-|~|to)\s*(\d{1,2}:\d{2})", re.IGNORECASE)
_DISTRICT_PATTERN = re.compile(r"([\u4e00-\u9fff]{1,6}區)")
_ORIGIN_ZH_PATTERN = re.compile(r"從\s*([^，。,.!?！？\s]+(?:站|車站|捷運站|商圈|夜市|公園|區)?)\s*出發")
_ORIGIN_EN_PATTERN = re.compile(
    r"\bfrom\s+([A-Za-z][A-Za-z0-9\s\-]{1,40}?)(?=(?:\s+(?:for|with|by|at|tonight|tomorrow|this|around)\b)|[,.!?]|$)",
    re.IGNORECASE,
)

_INTEREST_TAG_KEYWORDS = {
    "cafes": ["cafe", "cafes", "coffee", "咖啡", "咖啡廳"],
    "museums": ["museum", "museums", "博物館", "美術館"],
    "night-market": ["night market", "night markets", "夜市"],
    "food": ["food", "eat", "restaurant", "美食", "吃", "餐廳"],
    "shopping": ["shopping", "shop", "逛街", "購物"],
    "temples": ["temple", "temples", "寺", "廟"],
    "nature": ["nature", "park", "parks", "trail", "公園", "步道", "自然"],
}
_AVOID_PREFIXES = ("avoid", "no ", "skip", "不要", "避開", "別去", "不想")


def _normalize_time(value: str) -> str:
    hour_str, minute_str = value.split(":")
    return f"{int(hour_str):02d}:{minute_str}"


def _detect_companions(message_lower: str) -> str | None:
    if any(token in message_lower for token in ("solo", "myself", "一個人", "自己")):
        return "solo"
    if any(token in message_lower for token in ("date", "dating", "約會", "情侶")):
        return "date"
    if any(token in message_lower for token in ("family", "kids", "親子", "家庭")):
        return "family"
    if any(token in message_lower for token in ("friends", "friend", "朋友")):
        return "friends"
    return None


def _detect_budget_level(message_lower: str) -> str | None:
    if any(token in message_lower for token in ("cheap", "budget", "省錢", "便宜", "平價")):
        return "budget"
    if any(token in message_lower for token in ("luxury", "high-end", "奢華", "高級")):
        return "luxury"
    if any(token in message_lower for token in ("mid-range", "moderate", "中等", "一般")):
        return "mid"
    return None


def _detect_transport_mode(message_lower: str) -> str | None:
    if any(token in message_lower for token in ("mrt", "metro", "transit", "public transport", "捷運", "公車", "大眾運輸")):
        return "transit"
    if any(token in message_lower for token in ("walk", "walking", "步行")):
        return "walk"
    if any(token in message_lower for token in ("uber", "taxi", "計程車")):
        return "taxi"
    if any(token in message_lower for token in ("drive", "driving", "car", "開車")):
        return "drive"
    return None


def _detect_indoor_preference(message_lower: str) -> bool | None:
    if any(token in message_lower for token in ("indoor", "inside", "室內", "下雨")):
        return True
    if any(token in message_lower for token in ("outdoor", "outside", "戶外")):
        return False
    return None


def _detect_origin(message: str) -> str | None:
    zh_match = _ORIGIN_ZH_PATTERN.search(message)
    if zh_match:
        return zh_match.group(1).strip()

    en_match = _ORIGIN_EN_PATTERN.search(message)
    if en_match:
        return en_match.group(1).strip()
    return None


def _detect_district(message: str) -> str | None:
    match = _DISTRICT_PATTERN.search(message)
    if match:
        district = match.group(1)
        for prefix in ("想去", "去", "到", "在"):
            if district.startswith(prefix) and district.endswith("區"):
                district = district[len(prefix) :]
                break
        return district
    return None


def _detect_time_window(message_lower: str) -> TimeWindow | None:
    range_match = _TIME_RANGE_PATTERN.search(message_lower)
    if range_match:
        return TimeWindow(
            start_time=_normalize_time(range_match.group(1)),
            end_time=_normalize_time(range_match.group(2)),
        )

    if "今晚" in message_lower or "tonight" in message_lower:
        return TimeWindow(start_time="18:00", end_time="23:00")
    if "早上" in message_lower or "morning" in message_lower:
        return TimeWindow(start_time="09:00", end_time="12:00")
    if "下午" in message_lower or "afternoon" in message_lower:
        return TimeWindow(start_time="13:00", end_time="17:00")
    return None


def _collect_tags(message_lower: str, *, avoid: bool) -> list[str]:
    tags: list[str] = []
    for tag, keywords in _INTEREST_TAG_KEYWORDS.items():
        has_keyword = any(keyword in message_lower for keyword in keywords)
        if not has_keyword:
            continue
        if avoid:
            if any(prefix in message_lower for prefix in _AVOID_PREFIXES):
                tags.append(tag)
        else:
            tags.append(tag)
    return list(dict.fromkeys(tags))


def extract_preferences_from_text(message: str) -> Preferences:
    """Deterministically extract obvious preference deltas from text."""
    message_lower = message.lower()
    delta: dict[str, Any] = {}

    companions = _detect_companions(message_lower)
    if companions is not None:
        delta["companions"] = companions

    budget_level = _detect_budget_level(message_lower)
    if budget_level is not None:
        delta["budget_level"] = budget_level

    transport_mode = _detect_transport_mode(message_lower)
    if transport_mode is not None:
        delta["transport_mode"] = transport_mode

    indoor_preference = _detect_indoor_preference(message_lower)
    if indoor_preference is not None:
        delta["indoor_preference"] = indoor_preference

    origin = _detect_origin(message)
    if origin is not None:
        delta["origin"] = origin

    district = _detect_district(message)
    if district is not None:
        delta["district"] = district

    time_window = _detect_time_window(message_lower)
    if time_window is not None:
        delta["time_window"] = time_window.model_dump(exclude_none=True)

    interest_tags = _collect_tags(message_lower, avoid=False)
    if interest_tags:
        delta["interest_tags"] = interest_tags

    avoid_tags = _collect_tags(message_lower, avoid=True)
    if avoid_tags:
        delta["avoid_tags"] = avoid_tags

    delta["language"] = detect_language_hint(message)
    return Preferences.model_validate(delta)


def combine_preference_deltas(*deltas: Preferences) -> Preferences:
    """Combine multiple preference deltas without wiping omitted fields."""
    merged: dict[str, Any] = {}
    for delta in deltas:
        for field_name in delta.model_fields_set:
            value = getattr(delta, field_name)
            if field_name in {"interest_tags", "avoid_tags"}:
                merged[field_name] = list(
                    dict.fromkeys([*merged.get(field_name, []), *(value or [])])
                )
                continue
            if field_name == "time_window" and value is not None:
                existing = merged.get("time_window", {})
                existing_start = existing.get("start_time") if isinstance(existing, dict) else None
                existing_end = existing.get("end_time") if isinstance(existing, dict) else None
                merged[field_name] = {
                    "start_time": value.start_time or existing_start,
                    "end_time": value.end_time or existing_end,
                }
                continue
            merged[field_name] = value
    return Preferences.model_validate(merged)


def build_preference_extraction_prompt(
    message: str,
    current_preferences: Preferences | None,
    language_hint: str,
) -> str:
    current_payload = (
        current_preferences.model_dump(exclude_none=True, exclude_defaults=True)
        if current_preferences
        else {}
    )
    return (
        "Extract only the new or corrected user preference fields from the latest message.\n"
        "Return a single JSON object using only these keys when explicitly mentioned: "
        "companions, budget_level, transport_mode, indoor_preference, origin, district, "
        "time_window, interest_tags, avoid_tags, language.\n"
        "Do not invent missing fields. Prefer concise normalized values.\n"
        f"Language hint: {language_hint}\n"
        f"Current preferences: {current_payload}\n"
        f"Latest message: {message}"
    )


class PreferenceExtractor:
    """Structured preference delta extraction with Gemini as the default path."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client = client or llm_client

    async def extract(
        self,
        message: str,
        current_preferences: Preferences | None = None,
    ) -> Preferences:
        heuristic_delta = extract_preferences_from_text(message)
        llm_delta = await self._extract_with_llm(message, current_preferences)
        return combine_preference_deltas(llm_delta, heuristic_delta)

    async def _extract_with_llm(
        self,
        message: str,
        current_preferences: Preferences | None,
    ) -> Preferences:
        prompt = build_preference_extraction_prompt(
            message=message,
            current_preferences=current_preferences,
            language_hint=detect_language_hint(message),
        )
        try:
            payload = await self._client.generate_json(
                prompt,
                model=self._client.default_model,
            )
        except Exception:
            return Preferences()
        if not isinstance(payload, dict):
            return Preferences()
        return Preferences.model_validate(payload)


__all__ = [
    "PreferenceExtractor",
    "build_preference_extraction_prompt",
    "combine_preference_deltas",
    "extract_preferences_from_text",
]
