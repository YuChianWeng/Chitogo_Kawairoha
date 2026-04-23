from __future__ import annotations

from typing import Any

from app.chat.schemas import ChatCandidate, RoutingStatus
from app.orchestration.intents import Intent
from app.session.models import Itinerary, Preferences
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
_RELAXATION_LABELS_ZH = {
    "dropped_district": "擴大到整個台北",
    "dropped_primary_type": "放寬類型限制",
    "dropped_max_budget_level": "不限預算",
    "dropped_indoor_preference": "不限室內或室外",
    "dropped_open_now": "不限營業中",
}
_RELAXATION_LABELS_EN = {
    "dropped_district": "broadened the search beyond the original district",
    "dropped_primary_type": "relaxed the place type",
    "dropped_max_budget_level": "removed the budget cap",
    "dropped_indoor_preference": "removed the indoor or outdoor preference",
    "dropped_open_now": "stopped requiring places that are open right now",
}
_PRIMARY_TYPE_LABELS_ZH = {
    "art_gallery": "美術館",
    "bakery": "烘焙店",
    "bar": "酒吧",
    "cafe": "咖啡廳",
    "coffee_shop": "咖啡店",
    "dessert_shop": "甜點店",
    "department_store": "百貨公司",
    "hiking_area": "步道",
    "ice_cream_shop": "冰淇淋店",
    "japanese_restaurant": "日式餐廳",
    "market": "市場",
    "museum": "博物館",
    "park": "公園",
    "ramen_restaurant": "拉麵",
}
_PRIMARY_TYPE_LABELS_EN = {
    "art_gallery": "art galleries",
    "bakery": "bakeries",
    "bar": "bars",
    "cafe": "cafes",
    "coffee_shop": "coffee shops",
    "dessert_shop": "dessert shops",
    "department_store": "department stores",
    "hiking_area": "hiking areas",
    "ice_cream_shop": "ice cream shops",
    "japanese_restaurant": "Japanese restaurants",
    "market": "markets",
    "museum": "museums",
    "park": "parks",
    "ramen_restaurant": "ramen spots",
}
_CATEGORY_LABELS_ZH = {
    "attraction": "景點",
    "food": "餐廳",
    "lodging": "住宿",
    "nightlife": "夜生活去處",
    "shopping": "購物地點",
}
_CATEGORY_LABELS_EN = {
    "attraction": "attractions",
    "food": "food spots",
    "lodging": "places to stay",
    "nightlife": "nightlife spots",
    "shopping": "shopping spots",
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

    def compose_replan_clarification(
        self,
        *,
        preferences: Preferences,
        has_itinerary: bool,
        missing_fields: list[str] | None = None,
    ) -> str:
        language = preferences.language or "en"
        if not has_itinerary:
            return (
                "你目前還沒有可調整的行程，先告訴我出發地點、時段和想去的類型，我先幫你排一版。"
                if language == "zh-TW"
                else "There isn't an itinerary to edit yet. Give me a starting point, time window, and vibe first, and I'll build one."
            )
        if missing_fields and "stop_index" in missing_fields:
            return (
                "你想調整哪一站？可以直接說第一站、第二站，或最後一站。"
                if language == "zh-TW"
                else "Which stop do you want to change? You can say first stop, second stop, or last stop."
            )
        return (
            "請再說明你想怎麼調整目前的行程。"
            if language == "zh-TW"
            else "Tell me a bit more about how you want to change the current itinerary."
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

    def compose_recommendation_with_relaxation(
        self,
        *,
        places: list[ToolPlace],
        preferences: Preferences,
        relaxations: list[str],
        original_filters: dict[str, Any],
    ) -> tuple[str, list[ChatCandidate]]:
        candidates = [self._build_candidate(place, preferences) for place in places]
        if not relaxations:
            return self.compose_recommendation(places=places, preferences=preferences)

        top_names = ", ".join(candidate.name for candidate in candidates[:3])
        language = preferences.language or "en"
        original_target = self._describe_original_filters(
            original_filters=original_filters,
            language=language,
        )
        relaxed_scope = self._describe_relaxations(relaxations=relaxations, language=language)

        if language == "zh-TW":
            reply = f"{original_target}沒有找到更貼近的結果，先幫你{relaxed_scope}"
            if top_names:
                reply += f"，這幾家評價不錯：{top_names}。"
            else:
                reply += "。"
            return reply, candidates

        reply = f"I couldn't find a strong match for {original_target}, so I {relaxed_scope}"
        if top_names:
            reply += f". Good options now include {top_names}."
        else:
            reply += "."
        return reply, candidates

    def compose_itinerary(
        self,
        *,
        itinerary: Itinerary,
        routing_status: RoutingStatus,
        preferences: Preferences,
    ) -> str:
        language = preferences.language or "en"
        if language == "zh-TW":
            reply = f"我幫你排了一個 {len(itinerary.stops)} 站的行程：{itinerary.summary}。"
            if routing_status == "partial_fallback":
                reply += " 部分移動時間是估算值，但整體順序仍可直接參考。"
            elif routing_status == "failed":
                reply += " 路線時間目前抓不到完整資料，所以我先把停留順序排好了。"
            return reply
        reply = f"I mapped out a {len(itinerary.stops)}-stop itinerary: {itinerary.summary}."
        if routing_status == "partial_fallback":
            reply += " Some transfer times are estimated, but the overall order is still usable."
        elif routing_status == "failed":
            reply += " I couldn't get full routing data, so the visit order is grounded but leg times are limited."
        return reply

    def compose_replan(
        self,
        *,
        itinerary: Itinerary,
        routing_status: RoutingStatus,
        preferences: Preferences,
        operation: str,
        target_index: int | None,
    ) -> str:
        language = preferences.language or "en"
        if language == "zh-TW":
            if operation == "remove":
                reply = "我已經把指定站點移除，其他站點盡量保持不變。"
            elif operation == "insert":
                reply = "我已經把新站點插入目前的行程裡。"
            elif target_index is not None:
                reply = f"我已經把第 {target_index + 1} 站換掉，其他站點盡量保持不變。"
            else:
                reply = "我已經更新了行程。"
            if routing_status != "full":
                reply += " 部分移動時間是估算值。"
            return f"{reply} {itinerary.summary}。"

        if operation == "remove":
            reply = "I removed the requested stop and kept the rest of the plan as intact as possible."
        elif operation == "insert":
            reply = "I inserted a new stop into the current plan."
        elif target_index is not None:
            reply = f"I replaced stop {target_index + 1} and kept the rest of the plan as intact as possible."
        else:
            reply = "I updated the itinerary."
        if routing_status != "full":
            reply += " Some leg times are estimated."
        return f"{reply} {itinerary.summary}."

    def compose_replan_error(
        self,
        *,
        preferences: Preferences,
    ) -> str:
        if preferences.language == "zh-TW":
            return "我現在沒辦法安全地更新這份行程，請稍後再試一次。"
        return "I couldn't safely update the itinerary just now. Please try again."

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

    def _describe_original_filters(
        self,
        *,
        original_filters: dict[str, Any],
        language: str,
    ) -> str:
        district = original_filters.get("district")
        place_label = self._describe_place_target(original_filters=original_filters, language=language)

        if language == "zh-TW":
            if district and place_label:
                return f"在{district}找{place_label}時"
            if district:
                return f"在{district}找符合條件的地方時"
            if place_label:
                return f"找{place_label}時"
            return "原本的條件下"

        if district and place_label:
            return f"{place_label} in {district}"
        if district:
            return f"places in {district}"
        if place_label:
            return place_label
        return "your original filters"

    def _describe_place_target(
        self,
        *,
        original_filters: dict[str, Any],
        language: str,
    ) -> str | None:
        primary_type = original_filters.get("primary_type")
        if isinstance(primary_type, str) and primary_type:
            labels = _PRIMARY_TYPE_LABELS_ZH if language == "zh-TW" else _PRIMARY_TYPE_LABELS_EN
            return labels.get(primary_type, primary_type.replace("_", " "))

        keyword = original_filters.get("keyword")
        if isinstance(keyword, str) and keyword:
            return keyword

        internal_category = original_filters.get("internal_category")
        if isinstance(internal_category, str) and internal_category:
            labels = _CATEGORY_LABELS_ZH if language == "zh-TW" else _CATEGORY_LABELS_EN
            return labels.get(internal_category, internal_category.replace("_", " "))
        return None

    def _describe_relaxations(
        self,
        *,
        relaxations: list[str],
        language: str,
    ) -> str:
        labels = _RELAXATION_LABELS_ZH if language == "zh-TW" else _RELAXATION_LABELS_EN
        parts = [labels[item] for item in relaxations if item in labels]
        if not parts:
            return "稍微放寬條件" if language == "zh-TW" else "slightly broadened the search"
        if language == "zh-TW":
            return "、".join(parts)
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return f"{', '.join(parts[:-1])}, and {parts[-1]}"

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
