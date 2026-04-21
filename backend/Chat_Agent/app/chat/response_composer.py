from __future__ import annotations

from app.chat.schemas import ChatCandidate
from app.orchestration.intents import Intent
from app.session.models import Preferences
from app.tools.models import ToolPlace

_TAG_LABELS = {
    "cafes": "cafe",
    "museums": "museum",
    "night-market": "night market",
    "food": "food",
    "shopping": "shopping",
    "temples": "temples",
    "nature": "nature",
}


class ResponseComposer:
    """Small deterministic composer for Phase 5 recommendation replies."""

    def compose_clarification(
        self,
        *,
        missing_fields: list[str],
        preferences: Preferences,
    ) -> str:
        language = preferences.language or "en"
        prompts = {
            "origin": "想從哪裡出發？" if language == "zh-TW" else "Where should I start from?",
            "time_window": "想安排什麼時段？" if language == "zh-TW" else "What time window should I plan for?",
            "context": (
                "這次比較想走什麼風格，例如約會、朋友聚會、咖啡廳、美食或博物館？"
                if language == "zh-TW"
                else "What vibe should I optimize for, like a date, friends, cafes, food, or museums?"
            ),
            "stop_index": "想調整哪一站？" if language == "zh-TW" else "Which stop do you want to change?",
        }
        ordered = [prompts[field] for field in missing_fields if field in prompts]
        if not ordered:
            return (
                "請再補充一點需求，我才能更精準地推薦。"
                if language == "zh-TW"
                else "Tell me a bit more so I can recommend something more specific."
            )
        if language == "zh-TW":
            return "我還差幾個關鍵資訊：" + " ".join(ordered)
        return "I need a bit more detail before I recommend anything concrete: " + " ".join(ordered)

    def compose_general_chat(self, *, preferences: Preferences) -> str:
        if preferences.language == "zh-TW":
            return "我可以幫你找台北景點、餐廳或半日行程。直接告訴我出發地點、時段和想要的風格就可以。"
        return (
            "I can help with Taipei recommendations, food spots, or a short itinerary. "
            "Tell me your starting point, time window, and the kind of places you want."
        )

    def compose_explain(self, *, preferences: Preferences, candidate_names: list[str]) -> str:
        if preferences.language == "zh-TW":
            if candidate_names:
                return f"我主要是根據你目前的偏好來挑選，像是地區、預算和興趣；目前比較符合的是：{', '.join(candidate_names[:3])}。"
            return "我會根據你目前的地區、預算、交通與興趣偏好來挑選合適的推薦。"
        if candidate_names:
            return (
                "I’m basing the recommendations on your stated preferences like district, "
                f"budget, and interests. Right now the strongest matches are {', '.join(candidate_names[:3])}."
            )
        return "I’m choosing recommendations based on your current district, budget, transport, and interest preferences."

    def compose_replan_placeholder(
        self,
        *,
        stop_index: int | None,
        preferences: Preferences,
    ) -> str:
        if preferences.language == "zh-TW":
            if stop_index is not None:
                return f"我看得出你想調整第 {stop_index + 1} 站，但完整重排行程會在下一個階段實作。你可以先告訴我想換成哪種類型，我先幫你推薦候選地點。"
            return "我能辨識這是重排行程的需求，但完整替換站點還沒在這一階段啟用。你可以先說想換成哪種類型的地點。"
        if stop_index is not None:
            return (
                f"I can see you want to change stop {stop_index + 1}, but full replanning is not enabled in Phase 5 yet. "
                "Tell me what kind of replacement you want and I can suggest candidates."
            )
        return (
            "I can tell this is a replanning request, but full stop replacement is not enabled in Phase 5 yet. "
            "Tell me what kind of replacement you want and I can suggest candidates."
        )

    def compose_no_results(
        self,
        *,
        preferences: Preferences,
    ) -> str:
        if preferences.language == "zh-TW":
            return "我這次沒有找到很合適的結果。可以試著放寬地區、預算或類型條件，我再幫你重找。"
        return "I couldn't find a strong match with those constraints. Try loosening the district, budget, or type and I'll search again."

    def compose_tool_error(
        self,
        *,
        preferences: Preferences,
    ) -> str:
        if preferences.language == "zh-TW":
            return "我目前暫時拿不到推薦資料，稍後再試一次，或直接告訴我想去的地區和類型，我會換個方式幫你找。"
        return "I couldn't reach the recommendation service right now. Try again shortly, or tell me a district and place type and I'll try a broader search."

    def compose_recommendation(
        self,
        *,
        places: list[ToolPlace],
        preferences: Preferences,
    ) -> tuple[str, list[ChatCandidate]]:
        candidates = [self._build_candidate(place, preferences) for place in places]
        top_names = ", ".join(candidate.name for candidate in candidates[:3])
        language = preferences.language or "en"
        if language == "zh-TW":
            reply = (
                f"我先幫你整理了 {len(candidates)} 個比較合適的選擇：{top_names}。"
                if candidates
                else "我先幫你整理了一些合適的選擇。"
            )
            if preferences.district:
                reply += f" 這些都優先貼近 {preferences.district} 一帶的需求。"
            elif preferences.origin:
                reply += f" 我也有把從 {preferences.origin} 出發的便利性納入考量。"
        else:
            reply = (
                f"I found {len(candidates)} solid options to start with: {top_names}."
                if candidates
                else "I pulled together a few grounded options for you."
            )
            if preferences.district:
                reply += f" These lean toward {preferences.district}."
            elif preferences.origin:
                reply += f" I also kept convenience from {preferences.origin} in mind."
        return reply.strip(), candidates

    def _build_candidate(
        self,
        place: ToolPlace,
        preferences: Preferences,
    ) -> ChatCandidate:
        return ChatCandidate.from_tool_place(
            place,
            why_recommended=self._why_recommended(place, preferences),
        )

    def _why_recommended(
        self,
        place: ToolPlace,
        preferences: Preferences,
    ) -> str | None:
        language = preferences.language or "en"
        reasons: list[str] = []
        if preferences.district and place.district and preferences.district == place.district:
            reasons.append("同區順路" if language == "zh-TW" else "matches your target district")
        matched_tags = [
            _TAG_LABELS[tag]
            for tag in preferences.interest_tags
            if tag in _TAG_LABELS and self._matches_interest(place, tag)
        ]
        if matched_tags:
            if language == "zh-TW":
                reasons.append(f"符合你偏好的{matched_tags[0]}")
            else:
                reasons.append(f"fits your {matched_tags[0]} preference")
        if preferences.budget_level and place.budget_level and preferences.budget_level == place.budget_level:
            reasons.append("預算相符" if language == "zh-TW" else "fits your budget")
        if place.rating is not None:
            reasons.append(
                f"評分 {place.rating:.1f}" if language == "zh-TW" else f"rated {place.rating:.1f}"
            )
        if not reasons and place.category:
            reasons.append(
                f"{place.category} 類型" if language == "zh-TW" else f"strong {place.category} match"
            )
        return "，".join(reasons) if language == "zh-TW" else ", ".join(reasons) if reasons else None

    @staticmethod
    def _matches_interest(place: ToolPlace, tag: str) -> bool:
        haystack = " ".join(
            fragment.lower()
            for fragment in [
                place.name,
                place.category or "",
                place.primary_type or "",
            ]
        )
        if tag == "cafes":
            return "cafe" in haystack or "coffee" in haystack
        if tag == "museums":
            return "museum" in haystack or "gallery" in haystack
        if tag == "night-market":
            return "night" in haystack or "market" in haystack
        if tag == "food":
            return "food" in haystack or "restaurant" in haystack
        if tag == "shopping":
            return "shop" in haystack or "mall" in haystack
        if tag == "temples":
            return "temple" in haystack
        if tag == "nature":
            return "park" in haystack or "trail" in haystack or "nature" in haystack
        return False
