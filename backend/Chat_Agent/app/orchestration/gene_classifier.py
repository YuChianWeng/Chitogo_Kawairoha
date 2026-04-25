from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Scoring matrix: question -> {answer: [genes receiving +1]}
_SCORING_MATRIX: dict[str, dict[str, list[str]]] = {
    "Q1": {
        "A": ["珍珠奶茶"], 
        "B": ["甘蔗青茶", "文山包種茶"], 
        "C": ["深夜永和豆漿"]
    },
    "Q2": {
        "A": ["珍珠奶茶", "古早味彈珠汽水"], 
        "B": ["野生愛玉冰", "文山包種茶"]
    },
    "Q3": {
        "A": ["文山包種茶", "野生愛玉冰"], 
        "B": ["古早味彈珠汽水", "深夜永和豆漿", "甘蔗青茶"]
    },
    "Q4": {
        "A": ["文山包種茶", "珍珠奶茶"], 
        "B": ["甘蔗青茶", "古早味彈珠汽水"]
    },
    "Q5": {
        "A": ["文山包種茶", "深夜永和豆漿", "珍珠奶茶"], 
        "B": ["野生愛玉冰", "甘蔗青茶", "古早味彈珠汽水"]
    },
    "Q6": {
        "A": ["深夜永和豆漿"], 
        "B": ["野生愛玉冰", "古早味彈珠汽水", "甘蔗青茶"]
    },
    "Q7": {
        "A": ["野生愛玉冰"], 
        "B": ["珍珠奶茶", "甘蔗青茶", "文山包種茶"]
    },
    "Q8": {
        "A": ["甘蔗青茶", "深夜永和豆漿"], 
        "B": ["文山包種茶", "野生愛玉冰", "珍珠奶茶"]
    },
    "Q9": {
        "A": ["古早味彈珠汽水"], 
        "B": ["深夜永和豆漿", "文山包種茶", "野生愛玉冰"]
    },
}

GENE_MASCOT_MAP: dict[str, str] = {
    "文山包種茶": "wenqing_cat",
    "古早味彈珠汽水": "family_bear",
    "珍珠奶茶": "tourist_owl",
    "深夜永和豆漿": "night_fox",
    "甘蔗青茶": "daytrip_rabbit",
    "野生愛玉冰": "outdoor_deer",
}

GENE_DESCRIPTIONS: dict[str, str] = {
    "文山包種茶": "你就像一壺文山包種茶\n就像這款以清澈茶湯和淡雅蘭花香聞名的台灣名茶，你的靈魂散發著一種低調卻迷人的優雅氣質，悄悄地吸引著身邊的人。你不是那種靠華麗登場吸引目光的人，反而更像一陣輕柔的微風——自然、舒服，讓人一靠近就覺得放鬆又安心你的存在總是帶著一種恰到好處的溫暖與療癒感，不張揚，卻能在不知不覺中給人力量與靈感。就像品一口包種茶，清新回甘，越細細感受，越讓人著迷",
    "古早味彈珠汽水": "你就像一瓶古早味彈珠汽水\n像這款充滿代表性的氣泡飲料一樣，你的靈魂裡裝滿了噗滋噗滋冒不停的活力和藏不住的快樂！那股把彈珠往上頂的氣泡，就像你停不下來的滿滿能量——永遠準備好迎接下一場冒險，隨時隨地都能出發！你不只是去旅行，而是走到哪裡、就把哪裡變成驚喜製造機！總能創造出讓人「哇！」的一瞬間和滿滿笑聲，尤其最能逗樂小朋友。就像打開彈珠汽水那一刻「啵！」的一聲，你的熱情超有感染力，能把再平凡不過的小郊遊，瞬間變成一家人最難忘的核心回憶",
    "珍珠奶茶": "你就像一杯最經典的珍珠奶茶\n就像這款紅遍全世界的台灣代表飲品，你的靈魂完美融合了甜甜的幸福感、Q彈的活力，還有滿滿毫無保留的快樂！對不常來台北的你來說，每一次旅程都像是一場神聖儀式。\n你總是帶著滿滿期待、好奇心，還有一個超重要的任務——尋找最道地的美食、踩點最經典的地標！就像那個穿梭在熱鬧夜市裡、閃閃發亮的擬人化珍奶角色一樣，你總是興奮地探索每個角落，一邊喝著珍奶、一邊把旅程變成一場充滿驚喜與美味的冒險",
    "深夜永和豆漿": "你就像一碗深夜永和豆漿\n就像這款在夜幕降臨後溫暖無數人心的台灣經典飲品，你天生就是個夜貓子體質！當太陽下山、大多數人都已經進入夢鄉時，真正的你才正要醒來。在霓虹燈閃爍的街頭與城市的夜色中，你被喚醒、被點亮，整個人充滿活力，就像那個穿著可愛緊身衣、戴著霓虹墨鏡的角色一樣帥氣又有精神。你不只是「熬夜」，你是主宰夜晚的人——把原本平凡的深夜時光，變成充滿溫度、笑聲與共享回憶的特別時刻",
    "甘蔗青茶": "你就像一杯甘蔗青茶\n像這款台灣清爽飲品一樣，擁有清澈的茶感與恰到好處的甜味，你的靈魂充滿源源不絕的能量，以及對「高效率快樂」的追求。對你來說，一天就是一份珍貴的禮物你帶著明確的「任務感」迎接每一天——在有限的24小時裡，把快樂最大化、把精彩濃縮到最剛好的密度。就像畫面中那個行程滿滿、舉著「Go on the Go」旗幟的快閃旅人一樣，你的生活節奏輕快又精準，每一站都有目的，每一步都在創造驚喜你的存在就像一陣清新的風，不只讓人感到放鬆，還會不自覺被你帶動起來，一起享受那種純粹、無雜質的探索快樂與效率美學",
    "野生愛玉冰": "你就像一碗野生愛玉冰\n清爽、自然，還帶著一點山林系的靈氣，彷彿把整座森林的精華都裝進了你的靈魂裡！\n熱愛戶外的你，把每一次旅行都當成一場和大自然的浪漫約會——盡情吹風、曬太陽、感受山林與微風，就像那個站在森林裡開開心心的愛玉小精靈一樣自在又快樂\n你喜歡最真實、最純粹的事物，欣賞簡單卻有溫度的美好。\n對你來說，人生最珍貴的，往往不是轟轟烈烈的大場面，而是那些平凡卻閃閃發亮的小瞬間\n",
}

# Base affinity weights per gene: category -> float
GENE_BASE_AFFINITY: dict[str, dict[str, float]] = {
    "文山包種茶": {
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
    "古早味彈珠汽水": {
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
    "珍珠奶茶": {
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
    "深夜永和豆漿": {
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
    "甘蔗青茶": {
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
    "野生愛玉冰": {
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
