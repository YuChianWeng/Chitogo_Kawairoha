from __future__ import annotations

from app.session.models import Preferences
from app.tools.models import ToolPlace


def summarize_preferences(preferences: Preferences) -> str:
    parts: list[str] = []
    if preferences.origin:
        parts.append(f"origin={preferences.origin}")
    if preferences.district:
        parts.append(f"district={preferences.district}")
    if preferences.time_window:
        time_window = preferences.time_window.model_dump(exclude_none=True)
        if time_window:
            parts.append(f"time_window={time_window}")
    if preferences.companions:
        parts.append(f"companions={preferences.companions}")
    if preferences.budget_level:
        parts.append(f"budget={preferences.budget_level}")
    if preferences.transport_mode:
        parts.append(f"transport={preferences.transport_mode}")
    if preferences.indoor_preference is not None:
        parts.append(f"indoor_preference={preferences.indoor_preference}")
    if preferences.interest_tags:
        parts.append(f"interest_tags={preferences.interest_tags}")
    if preferences.avoid_tags:
        parts.append(f"avoid_tags={preferences.avoid_tags}")
    return ", ".join(parts) if parts else "no strong preferences yet"


def summarize_tool_places(places: list[ToolPlace], *, limit: int = 5) -> str:
    if not places:
        return "No candidate places were found."
    lines: list[str] = []
    for index, place in enumerate(places[:limit], start=1):
        fragments = [f"{index}. {place.name}"]
        if place.district:
            fragments.append(f"district={place.district}")
        if place.category:
            fragments.append(f"category={place.category}")
        if place.rating is not None:
            fragments.append(f"rating={place.rating}")
        if place.budget_level is not None:
            fragments.append(f"budget={place.budget_level}")
        lines.append(", ".join(fragments))
    return "\n".join(lines)


def build_recommendation_system_prompt(*, language_hint: str) -> str:
    return (
        "You are a Taipei travel assistant composing concise, grounded recommendation replies.\n"
        "Only use facts present in the provided tool results and preference summary.\n"
        "Do not invent districts, ratings, prices, opening hours, or transit details.\n"
        "Prefer two short paragraphs or a compact list-style answer in the user's language hint.\n"
        f"Language hint: {language_hint}"
    )


def build_recommendation_user_prompt(
    *,
    user_message: str,
    preferences: Preferences,
    candidates: list[ToolPlace],
) -> str:
    return (
        f"User message: {user_message}\n"
        f"Preferences: {summarize_preferences(preferences)}\n"
        "Candidate places:\n"
        f"{summarize_tool_places(candidates)}\n"
        "Write a concise recommendation reply that explains why these are a good fit."
    )
