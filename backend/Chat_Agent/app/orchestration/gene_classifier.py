from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Scoring matrix: question -> {answer: [genes receiving +1]}
_SCORING_MATRIX: dict[str, dict[str, list[str]]] = {
    "Q1": {"A": ["文清", "親子"], "B": ["野外", "一日"], "C": ["夜貓子"]},
    "Q2": {"A": ["文清"], "B": ["一日"]},
    "Q3": {"A": ["文清", "不常來"], "B": ["親子", "夜貓子"]},
    "Q4": {"A": ["文清", "夜貓子"], "B": ["親子"]},
    "Q5": {"A": ["不常來", "夜貓子"], "B": ["文清", "親子"]},
    "Q6": {"A": ["一日", "不常來"], "B": ["夜貓子"]},
    "Q7": {"A": ["文清"], "B": ["野外", "親子"]},
    "Q8": {"A": ["野外", "文清"], "B": ["一日", "不常來"]},
    "Q9": {"A": ["不常來"], "B": ["夜貓子", "文清"]},
}

GENE_MASCOT_MAP: dict[str, str] = {
    "文清": "wenqing_cat",
    "親子": "family_bear",
    "不常來": "tourist_owl",
    "夜貓子": "night_fox",
    "一日": "daytrip_rabbit",
    "野外": "outdoor_deer",
}

GENE_DESCRIPTIONS: dict[str, str] = {
    "文清": "你是文青旅人，喜歡咖啡廳、書店和藝文空間，在巷弄裡發現城市的詩意。",
    "親子": "你是親子旅人，重視溫馨體驗，親子同樂是旅遊最大的快樂。",
    "不常來": "你是初訪旅人，對台北充滿好奇，想把著名景點和隱藏版一次蒐羅。",
    "夜貓子": "你是夜貓族，夜晚才是你的主場，夜市、酒吧和深夜食堂是你的天堂。",
    "一日": "你是效率旅人，行程滿滿也不累，一天之內要把台北精華看個遍。",
    "野外": "你是戶外探索者，熱愛自然、山徑和公園，用雙腳感受城市的生命力。",
}

# Base affinity weights per gene: category -> float
GENE_BASE_AFFINITY: dict[str, dict[str, float]] = {
    "文清": {
        "cafe": 1.5,
        "bookstore": 1.5,
        "museum": 1.3,
        "restaurant": 1.0,
        "park": 1.0,
        "bar": 0.8,
        "nightmarket": 0.7,
        "landmark": 1.0,
        "temple": 0.9,
        "trail": 0.8,
        "market": 1.0,
        "aquarium": 0.9,
    },
    "親子": {
        "park": 1.4,
        "museum": 1.3,
        "aquarium": 1.5,
        "restaurant": 1.1,
        "cafe": 1.0,
        "landmark": 1.1,
        "market": 1.0,
        "temple": 0.9,
        "bookstore": 0.9,
        "trail": 1.1,
        "bar": 0.3,
        "nightmarket": 0.8,
    },
    "不常來": {
        "landmark": 1.5,
        "market": 1.4,
        "temple": 1.4,
        "nightmarket": 1.3,
        "museum": 1.2,
        "restaurant": 1.1,
        "cafe": 1.0,
        "park": 1.0,
        "aquarium": 1.1,
        "trail": 0.9,
        "bar": 1.0,
        "bookstore": 0.8,
    },
    "夜貓子": {
        "bar": 1.5,
        "nightmarket": 1.5,
        "restaurant": 1.2,
        "cafe": 1.0,
        "landmark": 0.8,
        "park": 0.7,
        "museum": 0.7,
        "temple": 0.6,
        "market": 1.0,
        "aquarium": 0.7,
        "bookstore": 0.8,
        "trail": 0.5,
    },
    "一日": {
        "market": 1.3,
        "park": 1.2,
        "landmark": 1.2,
        "restaurant": 1.1,
        "temple": 1.1,
        "nightmarket": 1.2,
        "museum": 1.0,
        "cafe": 1.0,
        "aquarium": 1.0,
        "trail": 0.9,
        "bar": 0.8,
        "bookstore": 0.9,
    },
    "野外": {
        "park": 1.5,
        "trail": 1.5,
        "landmark": 1.2,
        "temple": 1.1,
        "restaurant": 1.0,
        "cafe": 0.9,
        "market": 1.0,
        "museum": 0.8,
        "nightmarket": 0.8,
        "aquarium": 0.9,
        "bar": 0.6,
        "bookstore": 0.7,
    },
}

ALL_GENES = list(GENE_MASCOT_MAP.keys())


class TravelGeneClassifier:
    def classify(
        self,
        answers: dict[str, str],
    ) -> tuple[str, str, str]:
        """Return (gene, mascot_id, gene_description)."""
        scores: dict[str, int] = {g: 0 for g in ALL_GENES}

        for q_key, answer in answers.items():
            gene_list = _SCORING_MATRIX.get(q_key, {}).get(answer, [])
            for gene in gene_list:
                scores[gene] += 1

        max_score = max(scores.values())
        winners = [g for g, s in scores.items() if s == max_score]

        if len(winners) == 1:
            gene = winners[0]
        else:
            # Tiebreaker: pick gene that appears earliest in Q1 answer tie-break order
            gene = self._tiebreak(winners, answers)

        mascot = GENE_MASCOT_MAP[gene]
        description = GENE_DESCRIPTIONS[gene]
        return gene, mascot, description

    def _tiebreak(self, candidates: list[str], answers: dict[str, str]) -> str:
        # Prefer gene that got its first point from the earliest question
        for q_key in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9"]:
            answer = answers.get(q_key, "")
            gene_list = _SCORING_MATRIX.get(q_key, {}).get(answer, [])
            for gene in gene_list:
                if gene in candidates:
                    return gene
        return candidates[0]
