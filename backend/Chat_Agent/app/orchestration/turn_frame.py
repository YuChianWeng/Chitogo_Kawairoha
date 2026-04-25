from __future__ import annotations

import logging
import re
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.llm.client import llm_client
from app.orchestration.intents import Intent
from app.orchestration.preferences import _VALID_DISTRICTS
from app.orchestration.slots import extract_stop_index
from app.session.models import Itinerary, Preferences
from app.tools.models import InternalCategory, PlaceSort

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE_THRESHOLD = 0.6
_REPLACE_PATTERN = re.compile(r"(換成|換掉|改成|改到|替換|replace|swap|change|modify)", re.IGNORECASE)
_REMOVE_PATTERN = re.compile(r"(刪|刪掉|移除|移掉|skip|remove|delete)", re.IGNORECASE)
_INSERT_PATTERN = re.compile(r"(加入|加一個|新增|insert|add)", re.IGNORECASE)
_LAST_STOP_PATTERN = re.compile(r"(最後一站|last\s+stop)", re.IGNORECASE)
_TARGET_REFERENCE_TEXT_PATTERN = re.compile(
    r"(最後一站|last\s+stop|第\s*[一二三四五六七八九十兩两\d]+\s*(?:站|個|家|間))",
    re.IGNORECASE,
)
_SIMPLE_REPLACEMENT_RULES: tuple[tuple[re.Pattern[str], dict[str, Any]], ...] = (
    (
        re.compile(r"(日式餐廳|日本料理|日料|japanese\s+restaurant)", re.IGNORECASE),
        {
            "internal_category": "food",
            "primary_type": "japanese_restaurant",
        },
    ),
    (
        re.compile(r"(公園|park)", re.IGNORECASE),
        {
            "internal_category": "attraction",
            "primary_type": "park",
        },
    ),
    (
        re.compile(r"(景點|景區|attraction|tourist\s+attraction)", re.IGNORECASE),
        {
            "internal_category": "attraction",
        },
    ),
)
# Fields eligible to persist from a TurnIntentFrame into the session.
# interest_tags and avoid_tags are intentionally excluded because they are
# turn-specific constraints and must not pollute later turns (T033).
_STABLE_PREFERENCE_FIELDS = frozenset(
    {
        "origin",
        "district",
        "time_window",
        "companions",
        "budget_level",
        "transport_mode",
        "indoor_preference",
        "language",
    }
)


class PlaceConstraint(BaseModel):
    district: str | None = None
    internal_category: InternalCategory | None = None
    primary_type: str | None = Field(default=None, max_length=128)
    keyword: str | None = Field(default=None, max_length=80)
    vibe_tags: list[str] = Field(default_factory=list)
    min_mentions: int | None = Field(default=None, ge=0)
    sort: PlaceSort | None = None
    max_budget_level: int | None = Field(default=None, ge=0, le=4)
    indoor: bool | None = None
    open_now: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("district")
    @classmethod
    def validate_district(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if stripped not in _VALID_DISTRICTS:
            raise ValueError("district must be a supported Taipei district")
        return stripped

    @field_validator("primary_type", "keyword")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("vibe_tags")
    @classmethod
    def normalize_vibe_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tag_list(value)


class TargetReference(BaseModel):
    kind: Literal["index", "ordinal", "relative", "name", "unknown"]
    raw_text: str | None = None
    resolved_index: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("raw_text")
    @classmethod
    def strip_raw_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class VibeTagSelection(BaseModel):
    selected_tags: list[str] = Field(default_factory=list)
    rejected_tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fallback_strategy: Literal["none", "broaden_search", "social_sort_only"] = "none"

    model_config = ConfigDict(extra="forbid")

    @field_validator("selected_tags", "rejected_tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tag_list(value)


class CategoryMixItem(BaseModel):
    internal_category: InternalCategory
    primary_type: str | None = Field(default=None, max_length=128)
    min_count: int = Field(default=1, ge=1)
    weight: float = Field(default=1.0, gt=0.0)

    model_config = ConfigDict(extra="forbid")


class CandidateMatchDecision(BaseModel):
    candidate_id: int | str
    candidate_name: str = Field(..., min_length=1)
    matched: bool
    failed_fields: list[str] = Field(default_factory=list)
    constraint_summary: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("failed_fields")
    @classmethod
    def normalize_failed_fields(cls, value: list[str]) -> list[str]:
        return _normalize_string_list(value)


class TurnIntentFrame(BaseModel):
    intent: Intent
    source: Literal["regex", "llm", "hybrid"]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    stable_preference_delta: Preferences | None = None
    search_constraint: PlaceConstraint | None = None
    replacement_constraint: PlaceConstraint | None = None
    target_reference: TargetReference | None = None
    operation: Literal["replace", "insert", "remove"] | None = None
    category_mix: list[CategoryMixItem] = Field(default_factory=list)
    vibe_tag_selection: VibeTagSelection | None = None
    raw_user_message: str = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("missing_fields")
    @classmethod
    def normalize_missing_fields(cls, value: list[str]) -> list[str]:
        normalized = _normalize_string_list(value)
        return ["target_reference" if item == "stop_index" else item for item in normalized]

    @model_validator(mode="after")
    def validate_replan_requirements(self) -> TurnIntentFrame:
        if self.intent != Intent.REPLAN:
            return self
        if self.operation is None:
            raise ValueError("replan frames require operation")
        if self.needs_clarification:
            return self
        if self.operation in {"replace", "insert", "remove"}:
            if self.target_reference is None or self.target_reference.resolved_index is None:
                raise ValueError("replan frames require target_reference")
            if self.target_reference.confidence < _LOW_CONFIDENCE_THRESHOLD:
                raise ValueError("replan target_reference confidence is too low")
        return self


def stable_preference_delta_for_merge(frame: TurnIntentFrame) -> Preferences | None:
    return _sanitize_stable_preference_delta(frame.stable_preference_delta)


def validate_turn_intent_frame(
    frame: TurnIntentFrame,
    *,
    itinerary: Itinerary | None = None,
    known_vibe_tags: Sequence[str] | None = None,
) -> TurnIntentFrame:
    target_reference = frame.target_reference.model_copy(deep=True) if frame.target_reference else None
    search_constraint = (
        frame.search_constraint.model_copy(deep=True) if frame.search_constraint else None
    )
    replacement_constraint = (
        frame.replacement_constraint.model_copy(deep=True)
        if frame.replacement_constraint
        else None
    )
    vibe_tag_selection = (
        frame.vibe_tag_selection.model_copy(deep=True) if frame.vibe_tag_selection else None
    )
    stable_preference_delta = _sanitize_stable_preference_delta(frame.stable_preference_delta)
    missing_fields: list[str] = []

    if known_vibe_tags is not None:
        (
            search_constraint,
            replacement_constraint,
            vibe_tag_selection,
        ) = _apply_known_vibe_tag_catalog(
            search_constraint=search_constraint,
            replacement_constraint=replacement_constraint,
            vibe_tag_selection=vibe_tag_selection,
            known_vibe_tags=known_vibe_tags,
        )

    if frame.intent == Intent.REPLAN:
        if frame.operation is None:
            _append_missing_field(missing_fields, "operation")
        elif frame.operation in {"replace", "insert", "remove"}:
            if target_reference is None or target_reference.resolved_index is None:
                _append_missing_field(missing_fields, "target_reference")
            elif target_reference.confidence < _LOW_CONFIDENCE_THRESHOLD:
                _append_missing_field(missing_fields, "target_reference")
            elif itinerary is not None and target_reference.resolved_index >= len(itinerary.stops):
                target_reference = target_reference.model_copy(
                    update={
                        "resolved_index": None,
                        "confidence": min(target_reference.confidence, 0.3),
                    }
                )
                _append_missing_field(missing_fields, "target_reference")
        if frame.confidence < _LOW_CONFIDENCE_THRESHOLD and not missing_fields:
            _append_missing_field(
                missing_fields,
                "target_reference" if frame.operation in {"replace", "insert", "remove"} else "operation",
            )

    return TurnIntentFrame.model_validate(
        {
            **frame.model_dump(),
            "needs_clarification": bool(missing_fields),
            "missing_fields": missing_fields,
            "stable_preference_delta": (
                stable_preference_delta.model_dump() if stable_preference_delta else None
            ),
            "search_constraint": search_constraint.model_dump() if search_constraint else None,
            "replacement_constraint": (
                replacement_constraint.model_dump() if replacement_constraint else None
            ),
            "target_reference": target_reference.model_dump() if target_reference else None,
            "vibe_tag_selection": (
                vibe_tag_selection.model_dump() if vibe_tag_selection else None
            ),
        }
    )


async def extract_replan_turn_frame(
    message: str,
    itinerary: Itinerary,
    *,
    client: Any | None = None,
) -> TurnIntentFrame:
    regex_frame = validate_turn_intent_frame(
        _build_replan_regex_frame(message, itinerary),
        itinerary=itinerary,
    )
    if not regex_frame.needs_clarification:
        return regex_frame

    llm_frame = await _extract_replan_turn_frame_with_llm(
        message=message,
        itinerary=itinerary,
        client=client or llm_client,
    )
    if llm_frame is None:
        return regex_frame

    return validate_turn_intent_frame(
        _merge_replan_frames(regex_frame, llm_frame),
        itinerary=itinerary,
    )


async def select_known_vibe_tags(
    message: str,
    known_vibe_tags: Sequence[str],
    *,
    client: Any | None = None,
) -> VibeTagSelection:
    if not known_vibe_tags:
        return VibeTagSelection(
            selected_tags=[],
            rejected_tags=[],
            confidence=0.0,
            fallback_strategy="broaden_search",
        )

    prompt = (
        "Select only from the known vibe tags for the latest user message.\n"
        f"User message: {message}\n"
        f"Known vibe tags: {list(known_vibe_tags)}\n"
        "Return strict JSON with keys: selected_tags, rejected_tags, confidence, fallback_strategy.\n"
        "selected_tags must be a subset of the known vibe tags list.\n"
        "rejected_tags may include user-requested vibe words that are not in the known list.\n"
        'fallback_strategy must be one of: "none", "broaden_search", "social_sort_only".\n'
        "If nothing clearly matches, return selected_tags as an empty array.\n"
        "Return JSON only, without markdown."
    )
    try:
        payload = await (client or llm_client).generate_json(prompt)
    except Exception:
        logger.warning("turn frame vibe-tag selection error", exc_info=True)
        return VibeTagSelection(
            selected_tags=[],
            rejected_tags=[],
            confidence=0.0,
            fallback_strategy="broaden_search",
        )

    selection = _coerce_vibe_selection_payload(payload)
    _, _, validated_selection = _apply_known_vibe_tag_catalog(
        search_constraint=None,
        replacement_constraint=None,
        vibe_tag_selection=selection,
        known_vibe_tags=known_vibe_tags,
    )
    return validated_selection or VibeTagSelection(
        selected_tags=[],
        rejected_tags=[],
        confidence=0.0,
        fallback_strategy="broaden_search",
    )


def _build_replan_regex_frame(message: str, itinerary: Itinerary) -> TurnIntentFrame:
    detected_operation = _detect_replan_operation(message)
    operation = detected_operation or "replace"
    if detected_operation is None:
        logger.debug("turn frame regex defaulted operation to replace: %s", message[:120])
    target_reference = _extract_target_reference(message, itinerary)
    replacement_constraint = (
        _extract_simple_replacement_constraint(message)
        if operation in {"replace", "insert"}
        else None
    )
    confidence = 0.95 if target_reference is not None else 0.35
    needs_clarification = target_reference is None
    return TurnIntentFrame(
        intent=Intent.REPLAN,
        source="regex",
        confidence=confidence,
        needs_clarification=needs_clarification,
        missing_fields=["target_reference"] if needs_clarification else [],
        replacement_constraint=replacement_constraint,
        target_reference=target_reference,
        operation=operation,
        raw_user_message=message,
    )


def _detect_replan_operation(
    message: str,
) -> Literal["replace", "insert", "remove"] | None:
    if _REPLACE_PATTERN.search(message):
        return "replace"
    if _REMOVE_PATTERN.search(message):
        return "remove"
    if _INSERT_PATTERN.search(message):
        return "insert"
    return None


def _extract_target_reference(message: str, itinerary: Itinerary) -> TargetReference | None:
    last_match = _LAST_STOP_PATTERN.search(message)
    if last_match:
        return TargetReference(
            kind="relative",
            raw_text=last_match.group(0),
            resolved_index=len(itinerary.stops) - 1,
            confidence=1.0,
        )

    stop_index = extract_stop_index(message)
    if stop_index is None:
        return None

    raw_text = None
    reference_match = _TARGET_REFERENCE_TEXT_PATTERN.search(message)
    if reference_match:
        raw_text = reference_match.group(0)

    return TargetReference(
        kind="ordinal",
        raw_text=raw_text,
        resolved_index=stop_index,
        confidence=1.0,
    )


def _extract_simple_replacement_constraint(message: str) -> PlaceConstraint | None:
    for pattern, payload in _SIMPLE_REPLACEMENT_RULES:
        if pattern.search(message):
            return PlaceConstraint.model_validate(payload)
    return None


async def _extract_replan_turn_frame_with_llm(
    *,
    message: str,
    itinerary: Itinerary,
    client: Any,
) -> TurnIntentFrame | None:
    stops_payload = [
        {
            "index": stop.stop_index,
            "name": stop.venue_name,
            "category": stop.category,
            "arrival_time": stop.arrival_time,
        }
        for stop in itinerary.stops
    ]
    prompt = (
        "Parse the latest itinerary edit request into a structured TurnIntentFrame.\n"
        f"User message: {message}\n"
        f"Current itinerary stops: {stops_payload}\n"
        "Return strict JSON only.\n"
        "Required top-level keys: intent, source, confidence, needs_clarification, missing_fields, raw_user_message, operation, target_reference, replacement_constraint.\n"
        'intent must be "REPLAN". source must be "llm".\n'
        'operation must be one of "replace", "insert", "remove".\n'
        "target_reference must be null or an object with keys: kind, raw_text, resolved_index, confidence.\n"
        "replacement_constraint must be null or an object with keys: district, internal_category, primary_type, keyword, vibe_tags, min_mentions, sort, max_budget_level, indoor, open_now.\n"
        "Use zero-based indexes for resolved_index.\n"
        "Use null when the target or replacement type is unclear.\n"
        "Return JSON only, without markdown."
    )
    try:
        payload = await client.generate_json(prompt)
    except Exception:
        logger.warning("turn frame LLM extraction error", exc_info=True)
        return None

    try:
        return _coerce_llm_replan_payload(payload, message=message)
    except Exception:
        logger.warning("turn frame LLM payload error", exc_info=True)
        return None


def _coerce_llm_replan_payload(payload: object, *, message: str) -> TurnIntentFrame:
    if not isinstance(payload, dict):
        raise ValueError("LLM payload must be a JSON object")

    if "target_index" in payload or "insert_index" in payload:
        operation = _normalize_operation(payload.get("operation")) or "replace"
        target_index = _normalize_index(payload.get("target_index"))
        insert_index = _normalize_index(payload.get("insert_index"))
        if operation == "insert" and target_index is None and insert_index is not None:
            target_index = max(0, insert_index - 1) if insert_index > 0 else 0
        return TurnIntentFrame(
            intent=Intent.REPLAN,
            source="llm",
            confidence=_normalize_confidence(payload.get("confidence"), default=0.8),
            needs_clarification=bool(payload.get("needs_clarification")),
            missing_fields=_normalize_string_list(payload.get("missing_fields")),
            target_reference=(
                TargetReference(
                    kind="index",
                    raw_text=None,
                    resolved_index=target_index,
                    confidence=0.8,
                )
                if target_index is not None
                else None
            ),
            operation=operation,
            raw_user_message=message,
        )

    target_reference = _normalize_target_reference(payload.get("target_reference"))
    replacement_constraint = _normalize_place_constraint(payload.get("replacement_constraint"))
    search_constraint = _normalize_place_constraint(payload.get("search_constraint"))
    stable_preference_delta = _normalize_preferences(payload.get("stable_preference_delta"))
    vibe_tag_selection = _coerce_vibe_selection_payload(payload.get("vibe_tag_selection"))
    return TurnIntentFrame(
        intent=Intent.REPLAN,
        source="llm",
        confidence=_normalize_confidence(payload.get("confidence"), default=0.8),
        needs_clarification=bool(payload.get("needs_clarification")),
        missing_fields=_normalize_string_list(payload.get("missing_fields")),
        stable_preference_delta=stable_preference_delta,
        search_constraint=search_constraint,
        replacement_constraint=replacement_constraint,
        target_reference=target_reference,
        operation=_normalize_operation(payload.get("operation")) or "replace",
        category_mix=_normalize_category_mix(payload.get("category_mix")),
        vibe_tag_selection=vibe_tag_selection,
        raw_user_message=message,
    )


def _merge_replan_frames(regex_frame: TurnIntentFrame, llm_frame: TurnIntentFrame) -> TurnIntentFrame:
    return TurnIntentFrame.model_validate(
        {
            **regex_frame.model_dump(),
            "source": "hybrid",
            "confidence": max(regex_frame.confidence, llm_frame.confidence),
            "needs_clarification": False,
            "missing_fields": [],
            "stable_preference_delta": _dump_model_or_none(
                llm_frame.stable_preference_delta or regex_frame.stable_preference_delta
            ),
            "search_constraint": _dump_model_or_none(
                llm_frame.search_constraint or regex_frame.search_constraint
            ),
            "replacement_constraint": _dump_model_or_none(
                llm_frame.replacement_constraint or regex_frame.replacement_constraint
            ),
            "target_reference": _dump_model_or_none(
                llm_frame.target_reference or regex_frame.target_reference
            ),
            "operation": llm_frame.operation or regex_frame.operation,
            "category_mix": [
                item.model_dump()
                for item in (llm_frame.category_mix or regex_frame.category_mix)
            ],
            "vibe_tag_selection": _dump_model_or_none(
                llm_frame.vibe_tag_selection or regex_frame.vibe_tag_selection
            ),
            "raw_user_message": llm_frame.raw_user_message,
        }
    )


def _apply_known_vibe_tag_catalog(
    *,
    search_constraint: PlaceConstraint | None,
    replacement_constraint: PlaceConstraint | None,
    vibe_tag_selection: VibeTagSelection | None,
    known_vibe_tags: Sequence[str],
) -> tuple[PlaceConstraint | None, PlaceConstraint | None, VibeTagSelection | None]:
    known_map = {tag.casefold(): tag for tag in _normalize_tag_list(list(known_vibe_tags))}
    rejected_tags = list(vibe_tag_selection.rejected_tags) if vibe_tag_selection else []
    selected_tags = list(vibe_tag_selection.selected_tags) if vibe_tag_selection else []

    search_constraint, search_rejected = _filter_constraint_vibe_tags(search_constraint, known_map)
    replacement_constraint, replacement_rejected = _filter_constraint_vibe_tags(
        replacement_constraint,
        known_map,
    )
    rejected_tags.extend(search_rejected)
    rejected_tags.extend(replacement_rejected)

    normalized_selected: list[str] = []
    for tag in selected_tags:
        canonical = known_map.get(tag.casefold())
        if canonical is None:
            rejected_tags.append(tag)
            continue
        if canonical not in normalized_selected:
            normalized_selected.append(canonical)

    normalized_rejected = _normalize_tag_list(rejected_tags)
    if not normalized_selected and not normalized_rejected and vibe_tag_selection is None:
        return search_constraint, replacement_constraint, None

    fallback_strategy = "none"
    if not normalized_selected:
        fallback_strategy = (
            vibe_tag_selection.fallback_strategy
            if vibe_tag_selection and vibe_tag_selection.fallback_strategy != "none"
            else "broaden_search"
        )

    return (
        search_constraint,
        replacement_constraint,
        VibeTagSelection(
            selected_tags=normalized_selected,
            rejected_tags=normalized_rejected,
            confidence=vibe_tag_selection.confidence if vibe_tag_selection else 0.0,
            fallback_strategy=fallback_strategy,
        ),
    )


def _filter_constraint_vibe_tags(
    constraint: PlaceConstraint | None,
    known_map: dict[str, str],
) -> tuple[PlaceConstraint | None, list[str]]:
    if constraint is None or not constraint.vibe_tags:
        return constraint, []

    allowed: list[str] = []
    rejected: list[str] = []
    for tag in constraint.vibe_tags:
        canonical = known_map.get(tag.casefold())
        if canonical is None:
            rejected.append(tag)
            continue
        if canonical not in allowed:
            allowed.append(canonical)
    return constraint.model_copy(update={"vibe_tags": allowed}), rejected


def _sanitize_stable_preference_delta(delta: Preferences | None) -> Preferences | None:
    if delta is None:
        return None
    payload: dict[str, Any] = {}
    for field_name in _STABLE_PREFERENCE_FIELDS:
        if field_name not in delta.model_fields_set:
            continue
        value = getattr(delta, field_name)
        if value is None:
            continue
        payload[field_name] = value
    if not payload:
        return None
    return Preferences.model_validate(payload)


def _normalize_target_reference(value: object) -> TargetReference | None:
    if value is None:
        return None
    if isinstance(value, TargetReference):
        return value
    if not isinstance(value, dict):
        return None
    return TargetReference.model_validate(value)


def _normalize_place_constraint(value: object) -> PlaceConstraint | None:
    if value is None:
        return None
    if isinstance(value, PlaceConstraint):
        return value
    if not isinstance(value, dict):
        return None
    return PlaceConstraint.model_validate(value)


def _normalize_preferences(value: object) -> Preferences | None:
    if value is None:
        return None
    if isinstance(value, Preferences):
        return value
    if not isinstance(value, dict):
        return None
    return Preferences.model_validate(value)


def _normalize_category_mix(value: object) -> list[CategoryMixItem]:
    if not isinstance(value, list):
        return []
    items: list[CategoryMixItem] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        items.append(CategoryMixItem.model_validate(item))
    return items


def _coerce_vibe_selection_payload(payload: object) -> VibeTagSelection | None:
    if payload is None:
        return None
    if isinstance(payload, VibeTagSelection):
        return payload
    if not isinstance(payload, dict):
        return None
    selected_tags = payload.get("selected_tags", payload.get("tags", []))
    rejected_tags = payload.get("rejected_tags", [])
    return VibeTagSelection(
        selected_tags=_normalize_tag_list(selected_tags if isinstance(selected_tags, list) else []),
        rejected_tags=_normalize_tag_list(rejected_tags if isinstance(rejected_tags, list) else []),
        confidence=_normalize_confidence(payload.get("confidence"), default=0.0),
        fallback_strategy=_normalize_fallback_strategy(payload.get("fallback_strategy")),
    )


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped or stripped in normalized:
            continue
        normalized.append(stripped)
    return normalized


def _normalize_tag_list(value: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped or stripped in normalized:
            continue
        normalized.append(stripped)
    return normalized


def _normalize_confidence(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return float(value)
    return default


def _normalize_index(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _normalize_operation(
    value: object,
) -> Literal["replace", "insert", "remove"] | None:
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in {"replace", "insert", "remove"}:
        return lowered  # type: ignore[return-value]
    return None


def _normalize_fallback_strategy(value: object) -> Literal["none", "broaden_search", "social_sort_only"]:
    if isinstance(value, str) and value in {"none", "broaden_search", "social_sort_only"}:
        return value  # type: ignore[return-value]
    return "broaden_search"


def _dump_model_or_none(value: BaseModel | None) -> dict[str, Any] | None:
    return value.model_dump() if value is not None else None


def _append_missing_field(missing_fields: list[str], field_name: str) -> None:
    if field_name not in missing_fields:
        missing_fields.append(field_name)


__all__ = [
    "CandidateMatchDecision",
    "CategoryMixItem",
    "PlaceConstraint",
    "TargetReference",
    "TurnIntentFrame",
    "VibeTagSelection",
    "extract_replan_turn_frame",
    "select_known_vibe_tags",
    "stable_preference_delta_for_merge",
    "validate_turn_intent_frame",
]
