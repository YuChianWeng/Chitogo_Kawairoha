from __future__ import annotations

from app.session.models import Preferences, Session
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


def build_session_context_block(session: Session, preferences: Preferences) -> str:
    """Compact context injected before each LLM call so the model never asks for known info."""
    lines: list[str] = []

    if session.user_location:
        lat = session.user_location.get("lat")
        lng = session.user_location.get("lng")
        district = preferences.district or "Taipei"
        lines.append(f"User current location: {district} (~{lat:.3f}, {lng:.3f}) — do NOT ask where to start")

    elif preferences.origin:
        lines.append(f"User origin: {preferences.origin} — do NOT ask where to start")

    if session.last_transport_config:
        tc = session.last_transport_config
        lines.append(f"Transport: {tc.mode}, max {tc.max_minutes_per_leg} min per leg — already set")
    elif preferences.transport_mode:
        lines.append(f"Transport preference: {preferences.transport_mode}")

    if session.return_time:
        dest = session.return_destination or "home"
        lines.append(f"Must return to {dest} by {session.return_time}")

    if session.visited_stops:
        visited_names = [s.venue_name for s in session.visited_stops[-5:]]
        lines.append(f"Already visited today: {', '.join(visited_names)} — avoid re-suggesting these")

    if not lines:
        return ""

    return "Session context (use this; do NOT re-ask for any of it):\n" + "\n".join(
        f"- {line}" for line in lines
    )


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
