from __future__ import annotations

import re
from typing import Any

from app.llm.client import LLMClient, llm_client
from app.orchestration.language import detect_language_hint
from app.session.models import Preferences

_DISTRICT_PATTERN = re.compile(r"([\u4e00-\u9fff]{2,3}區)")
_DISTRICT_DEPARTURE_PATTERN = re.compile(r"從\s*([\u4e00-\u9fff]{2,3}區)\s*出發")
_AFTERNOON_PATTERN = re.compile(r"(下午(?:出發)?|afternoon)", re.IGNORECASE)
_VALID_DISTRICTS = frozenset(
    {
        "中山區",
        "大安區",
        "中正區",
        "士林區",
        "信義區",
        "內湖區",
        "萬華區",
        "北投區",
        "大同區",
        "南港區",
        "文山區",
        "松山區",
    }
)
_COMPANION_ALIASES = {
    "solo": "solo",
    "one": "solo",
    "alone": "solo",
    "自己": "solo",
    "一個人": "solo",
    "date": "date",
    "dating": "date",
    "couple": "date",
    "約會": "date",
    "情侶": "date",
    "family": "family",
    "families": "family",
    "家人": "family",
    "家庭": "family",
    "親子": "family",
    "friends": "friends",
    "friend": "friends",
    "朋友": "friends",
    "朋友們": "friends",
}
_BUDGET_ALIASES = {
    "budget": "budget",
    "cheap": "budget",
    "affordable": "budget",
    "low": "budget",
    "便宜": "budget",
    "省錢": "budget",
    "平價": "budget",
    "mid": "mid",
    "moderate": "mid",
    "medium": "mid",
    "中等": "mid",
    "中價": "mid",
    "普通": "mid",
    "luxury": "luxury",
    "premium": "luxury",
    "expensive": "luxury",
    "高級": "luxury",
    "高檔": "luxury",
}
_TRANSPORT_ALIASES = {
    "transit": "transit",
    "public transit": "transit",
    "public_transport": "transit",
    "metro": "transit",
    "subway": "transit",
    "train": "transit",
    "bus": "transit",
    "捷運": "transit",
    "大眾運輸": "transit",
    "公車": "transit",
    "walk": "walk",
    "walking": "walk",
    "步行": "walk",
    "走路": "walk",
    "taxi": "taxi",
    "cab": "taxi",
    "計程車": "taxi",
    "drive": "drive",
    "driving": "drive",
    "car": "drive",
    "開車": "drive",
}
_INTEREST_TAG_ALIASES = {
    "cafes": "cafes",
    "cafe": "cafes",
    "coffee": "cafes",
    "咖啡": "cafes",
    "咖啡廳": "cafes",
    "museums": "museums",
    "museum": "museums",
    "博物館": "museums",
    "night-market": "night-market",
    "night market": "night-market",
    "夜市": "night-market",
    "food": "food",
    "美食": "food",
    "餐廳": "food",
    "shopping": "shopping",
    "shop": "shopping",
    "購物": "shopping",
    "temples": "temples",
    "temple": "temples",
    "寺廟": "temples",
    "nature": "nature",
    "park": "nature",
    "自然": "nature",
    "公園": "nature",
}
_MESSAGE_INTEREST_HINT_ALIASES = (
    ("日式餐廳", "日式"),
    ("日本料理", "日式"),
    ("日料", "日式"),
    ("日式", "日式"),
    ("拉麵", "拉麵"),
    ("壽司", "壽司"),
    ("居酒屋", "居酒屋"),
    ("公園", "nature"),
)
_INTEREST_TAG_EQUIVALENTS = {
    "日式": frozenset({"日式", "日式餐廳", "日本料理", "日料", "japanese"}),
    "拉麵": frozenset({"拉麵", "ramen"}),
    "壽司": frozenset({"壽司", "sushi"}),
    "居酒屋": frozenset({"居酒屋", "izakaya"}),
}


def _detect_district(message: str) -> str | None:
    for district in _VALID_DISTRICTS:
        if district in message:
            return district
    match = _DISTRICT_PATTERN.search(message)
    if match:
        district = match.group(1)
        for prefix in ("從", "想去", "去", "到", "在"):
            if district.startswith(prefix) and district.endswith("區"):
                district = district[len(prefix) :]
                break
        if district in _VALID_DISTRICTS:
            return district
    return None


def _detect_departure_origin(message: str) -> str | None:
    match = _DISTRICT_DEPARTURE_PATTERN.search(message)
    if not match:
        return None
    district = match.group(1)
    return district if district in _VALID_DISTRICTS else None


def _coerce_first_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _normalize_alias(value: object, aliases: dict[str, str]) -> str | None:
    normalized = _coerce_first_string(value)
    if normalized is None:
        return None
    return aliases.get(normalized.casefold(), aliases.get(normalized, normalized))


def _normalize_tag_list(value: object) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped:
            continue
        normalized_tag = _INTEREST_TAG_ALIASES.get(
            stripped.casefold(),
            _INTEREST_TAG_ALIASES.get(stripped, stripped.casefold()),
        )
        if normalized_tag not in normalized:
            normalized.append(normalized_tag)
    return normalized


def _detect_interest_tags_from_message(message: str) -> list[str]:
    detected: list[str] = []
    for phrase, normalized_tag in _MESSAGE_INTEREST_HINT_ALIASES:
        if phrase in message and normalized_tag not in detected:
            detected.append(normalized_tag)
    return detected


def _has_equivalent_interest_tag(tags: list[str], candidate: str) -> bool:
    equivalents = _INTEREST_TAG_EQUIVALENTS.get(candidate, frozenset({candidate}))
    equivalent_casefolded = {tag.casefold() for tag in equivalents}
    return any(tag.casefold() in equivalent_casefolded for tag in tags)


def _infer_time_window_from_message(message: str) -> dict[str, str] | None:
    if _AFTERNOON_PATTERN.search(message):
        return {
            "start_time": "13:00",
            "end_time": "18:00",
        }
    return None


def _normalize_time_window(
    value: object,
    *,
    message: str,
) -> dict[str, str | None] | None:
    inferred = _infer_time_window_from_message(message)

    if isinstance(value, dict):
        start_time = _coerce_first_string(value.get("start_time"))
        end_time = _coerce_first_string(value.get("end_time"))
        if inferred is not None:
            start_time = start_time or inferred["start_time"]
            end_time = end_time or inferred["end_time"]
        if start_time is None and end_time is None:
            return None
        return {
            "start_time": start_time,
            "end_time": end_time,
        }

    scalar_value = _coerce_first_string(value)
    if scalar_value is not None and _AFTERNOON_PATTERN.search(scalar_value):
        return {
            "start_time": "13:00",
            "end_time": "18:00",
        }

    return inferred


def _normalize_preference_payload(message: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for field_name in ("origin", "district", "language"):
        if field_name in normalized:
            normalized[field_name] = _coerce_first_string(normalized[field_name])

    for field_name, aliases in (
        ("companions", _COMPANION_ALIASES),
        ("budget_level", _BUDGET_ALIASES),
        ("transport_mode", _TRANSPORT_ALIASES),
    ):
        if field_name in normalized:
            normalized[field_name] = _normalize_alias(normalized[field_name], aliases)

    for field_name in ("interest_tags", "avoid_tags"):
        if field_name in normalized:
            normalized[field_name] = _normalize_tag_list(normalized[field_name])

    normalized_time_window = _normalize_time_window(
        normalized.get("time_window"),
        message=message,
    )
    if normalized_time_window is not None:
        normalized["time_window"] = normalized_time_window
    elif "time_window" in normalized:
        normalized["time_window"] = None

    detected_interest_tags = _detect_interest_tags_from_message(message)
    if detected_interest_tags:
        existing_interest_tags = list(normalized.get("interest_tags") or [])
        for detected_tag in detected_interest_tags:
            if not _has_equivalent_interest_tag(existing_interest_tags, detected_tag):
                existing_interest_tags.append(detected_tag)
        normalized["interest_tags"] = existing_interest_tags

    detected_district = _detect_district(message)
    if normalized.get("district") not in _VALID_DISTRICTS:
        normalized["district"] = detected_district

    if not normalized.get("origin"):
        normalized["origin"] = _detect_departure_origin(message)

    return normalized


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
        "Return a single strict JSON object using only these keys when explicitly mentioned or corrected: "
        "companions, budget_level, transport_mode, indoor_preference, origin, district, "
        "time_window, interest_tags, avoid_tags, language.\n"
        "Do not invent missing fields. Prefer concise normalized values.\n"
        "Valid districts: 中山區, 大安區, 中正區, 士林區, 信義區, 內湖區, 萬華區, 北投區, 大同區, 南港區, 文山區, 松山區. "
        "district must be exactly one of these or null.\n"
        'Valid companions values: "solo", "date", "family", "friends".\n'
        'Valid budget_level values: "budget", "mid", "luxury".\n'
        'Valid transport_mode values: "transit", "walk", "taxi", "drive".\n'
        'Valid interest_tags values: "cafes", "museums", "night-market", "food", "shopping", "temples", "nature".\n'
        "When the user specifies a concrete cuisine or place type, preserve that specificity in "
        'interest_tags instead of collapsing it to a generic tag, for example: "日式", "日式餐廳", '
        '"拉麵", "壽司", "居酒屋", "咖啡廳", "酒吧", "博物館".\n'
        'time_window format: {"start_time": "HH:MM", "end_time": "HH:MM"}.\n'
        "Return JSON only, without markdown.\n"
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
        return await self._extract_with_llm(message, current_preferences)

    async def _extract_with_llm(
        self,
        message: str,
        current_preferences: Preferences | None,
    ) -> Preferences:
        language_hint = detect_language_hint(message)
        prompt = build_preference_extraction_prompt(
            message=message,
            current_preferences=current_preferences,
            language_hint=language_hint,
        )
        try:
            payload = await self._client.generate_json(prompt)
        except Exception:
            return Preferences(language=language_hint)

        try:
            if not isinstance(payload, dict):
                raise TypeError("preference payload must be an object")
            normalized_payload = _normalize_preference_payload(message, payload)
            if normalized_payload.get("district") not in {None, *_VALID_DISTRICTS}:
                normalized_payload["district"] = None
            normalized_payload.setdefault("language", language_hint)
            return Preferences.model_validate(normalized_payload)
        except Exception:
            return Preferences(language=language_hint)


__all__ = [
    "PreferenceExtractor",
    "build_preference_extraction_prompt",
    "combine_preference_deltas",
]
