from __future__ import annotations

from typing import Any

from app.orchestration.language import detect_language_hint
from app.orchestration.slots import extract_stop_index


def _extract_prompt_value(prompt: str, prefix: str) -> str:
    for line in reversed(prompt.splitlines()):
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


class DisabledLLMClient:
    async def generate_json(self, *_: object, **__: object) -> dict[str, Any]:
        raise RuntimeError("disabled")


class StaticJSONClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def generate_json(self, *_: object, **__: object) -> dict[str, Any]:
        return self.payload


class ScriptedClassifierClient:
    async def generate_json(self, prompt: str, **_: object) -> dict[str, Any]:
        message = _extract_prompt_value(prompt, "message:")
        lower_message = message.lower()

        if any(token in lower_message for token in ("why", "explain")) or any(
            token in message for token in ("為什麼", "解釋", "說明")
        ):
            return {
                "intent": "EXPLAIN",
                "confidence": 0.9,
                "needs_clarification": False,
                "missing_fields": [],
                "extracted_slots": {"subject": None},
            }

        if any(token in lower_message for token in ("replace", "swap", "remove", "delete", "insert")) or any(
            token in message for token in ("換", "刪", "移除", "加入", "新增", "改一下行程")
        ):
            stop_index = extract_stop_index(message)
            if stop_index is None and "最後一站" in message:
                stop_index = 2
            return {
                "intent": "REPLAN",
                "confidence": 0.92,
                "needs_clarification": stop_index is None,
                "missing_fields": ["stop_index"] if stop_index is None else [],
                "extracted_slots": {
                    "stop_index": stop_index,
                    "change_request": message,
                },
            }

        if any(token in lower_message for token in ("itinerary", "plan", "trip", "schedule")) or any(
            token in message for token in ("行程", "排", "安排")
        ):
            slots: dict[str, Any] = {
                "origin": "台北車站" if "台北車站" in message else None,
                "district": "萬華區" if "萬華區" in message else None,
                "time_window": (
                    {"start_time": "18:00", "end_time": "23:00"}
                    if "今晚" in message or "tonight" in lower_message
                    else None
                ),
                "companions": None,
                "budget_level": None,
                "transport_mode": None,
                "interest_tags": ["cafes"] if ("咖啡" in message or "cafe" in lower_message) else [],
                "avoid_tags": [],
            }
            missing_fields: list[str] = []
            if slots["origin"] is None:
                missing_fields.append("origin")
            if slots["time_window"] is None:
                missing_fields.append("time_window")
            if not any(
                [
                    slots["district"],
                    slots["companions"],
                    slots["budget_level"],
                    slots["transport_mode"],
                    slots["interest_tags"],
                    slots["avoid_tags"],
                ]
            ):
                missing_fields.append("context")
            if len(missing_fields) < 2:
                missing_fields = []
            return {
                "intent": "GENERATE_ITINERARY",
                "confidence": 0.9,
                "needs_clarification": bool(missing_fields),
                "missing_fields": missing_fields,
                "extracted_slots": slots,
            }

        return {
            "intent": "CHAT_GENERAL",
            "confidence": 0.8,
            "needs_clarification": False,
            "missing_fields": [],
            "extracted_slots": {"topic": message},
        }


class ScriptedPreferenceClient:
    async def generate_json(self, prompt: str, **_: object) -> dict[str, Any]:
        message = _extract_prompt_value(prompt, "Latest message:")
        lower_message = message.lower()
        payload: dict[str, Any] = {
            "language": detect_language_hint(message),
        }

        if "台北車站" in message:
            payload["origin"] = "台北車站"
        if "台北101" in message:
            payload["origin"] = "台北101"
        if "萬華區" in message:
            payload["district"] = "萬華區"
        if "和朋友" in message or "朋友" in message or "friends" in lower_message:
            payload["companions"] = "friends"
        if "捷運" in message or "mrt" in lower_message or "metro" in lower_message:
            payload["transport_mode"] = "transit"
        if "今晚" in message or "tonight" in lower_message:
            payload["time_window"] = {
                "start_time": "18:00",
                "end_time": "23:00",
            }

        interest_tags: list[str] = []
        if "咖啡" in message or "cafe" in lower_message or "coffee" in lower_message:
            interest_tags.append("cafes")
        if "博物館" in message or "museum" in lower_message:
            interest_tags.append("museums")
        if interest_tags:
            payload["interest_tags"] = interest_tags
        return payload
