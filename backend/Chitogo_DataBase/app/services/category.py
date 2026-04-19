from __future__ import annotations

from collections.abc import Iterable


INTERNAL_CATEGORIES = (
    "attraction",
    "food",
    "shopping",
    "lodging",
    "transport",
    "nightlife",
    "other",
)

CATEGORY_LABELS: dict[str, str] = {
    "attraction": "Attraction",
    "food": "Food & Drink",
    "shopping": "Shopping",
    "lodging": "Lodging",
    "transport": "Transport",
    "nightlife": "Nightlife",
    "other": "Other",
}

REPRESENTATIVE_TYPES: dict[str, list[str]] = {
    "attraction": ["tourist_attraction", "museum", "park", "art_gallery"],
    "food": ["restaurant", "cafe", "bakery", "dessert_shop"],
    "shopping": ["shopping_mall", "market", "store"],
    "lodging": ["hotel", "hostel", "inn"],
    "transport": ["subway_station", "train_station", "bus_station", "parking"],
    "nightlife": ["bar", "pub", "night_club"],
    "other": [],
}

CATEGORY_MAP: dict[str, str] = {
    # transport
    "subway_station": "transport",
    "train_station": "transport",
    "bus_station": "transport",
    "bus_stop": "transport",
    "transit_station": "transport",
    "parking": "transport",
    "parking_lot": "transport",
    "parking_garage": "transport",
    # lodging
    "hotel": "lodging",
    "lodging": "lodging",
    "hostel": "lodging",
    "inn": "lodging",
    "motel": "lodging",
    # shopping
    "shopping_mall": "shopping",
    "market": "shopping",
    "store": "shopping",
    "department_store": "shopping",
    "clothing_store": "shopping",
    "book_store": "shopping",
    "convenience_store": "shopping",
    "home_goods_store": "shopping",
    "florist": "shopping",
    "garden_center": "shopping",
    "supermarket": "shopping",
    "electronics_store": "shopping",
    "jewelry_store": "shopping",
    # nightlife explicitly outranks food for these venue types
    "bar": "nightlife",
    "pub": "nightlife",
    "night_club": "nightlife",
    # food
    "restaurant": "food",
    "cafe": "food",
    "coffee_shop": "food",
    "bakery": "food",
    "dessert_shop": "food",
    "cake_shop": "food",
    "pastry_shop": "food",
    "food_store": "food",
    "taiwanese_restaurant": "food",
    "japanese_restaurant": "food",
    "chinese_restaurant": "food",
    "hot_pot_restaurant": "food",
    "brunch_restaurant": "food",
    "fast_food_restaurant": "food",
    "ramen_restaurant": "food",
    "bistro": "food",
    "deli": "food",
    "ice_cream_shop": "food",
    "food_court": "food",
    "pizza_restaurant": "food",
    "sushi_restaurant": "food",
    "breakfast_restaurant": "food",
    "buffet_restaurant": "food",
    "seafood_restaurant": "food",
    "steak_house": "food",
    "vegetarian_restaurant": "food",
    "tea_house": "food",
    # attraction
    "tourist_attraction": "attraction",
    "museum": "attraction",
    "art_gallery": "attraction",
    "park": "attraction",
    "historical_landmark": "attraction",
    "historical_place": "attraction",
    "scenic_spot": "attraction",
    "cultural_landmark": "attraction",
    "art_museum": "attraction",
    "city_park": "attraction",
    "hiking_area": "attraction",
    "zoo": "attraction",
    "aquarium": "attraction",
    "amusement_park": "attraction",
    "botanical_garden": "attraction",
    "temple": "attraction",
    "shrine": "attraction",
    "church": "attraction",
    "scenic_viewpoint": "attraction",
    "hot_spring": "attraction",
    "cultural_center": "attraction",
    "point_of_interest": "attraction",
}

BUDGET_RANK = {
    "PRICE_LEVEL_FREE": 0,
    "INEXPENSIVE": 1,
    "MODERATE": 2,
    "EXPENSIVE": 3,
    "VERY_EXPENSIVE": 4,
}


def _iter_place_types(types_json: object) -> Iterable[str]:
    if not isinstance(types_json, list):
        return ()
    return (value for value in types_json if isinstance(value, str))


def map_category(primary_type: str | None, types_json: object = None) -> str:
    if primary_type in CATEGORY_MAP:
        return CATEGORY_MAP[primary_type]

    for place_type in _iter_place_types(types_json):
        if place_type in CATEGORY_MAP:
            return CATEGORY_MAP[place_type]

    return "other"


def budget_rank(budget_level: str | None) -> int | None:
    if budget_level is None:
        return None
    return BUDGET_RANK.get(budget_level)


def get_category_metadata() -> list[dict[str, object]]:
    return [
        {
            "value": category,
            "label": CATEGORY_LABELS[category],
            "representative_types": list(REPRESENTATIVE_TYPES[category]),
        }
        for category in INTERNAL_CATEGORIES
    ]
