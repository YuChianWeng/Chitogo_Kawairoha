"""Base protocol and helpers for candidate venue providers."""

from __future__ import annotations

import hashlib
from typing import Protocol

from app.models.db import Venue


class CandidateProvider(Protocol):
    """Any source that can return candidate venues for a query."""

    async def fetch(
        self,
        district: str,
        interests: list[str],
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> list[Venue]:
        """Return a list of venues matching the query."""
        ...


# ---- Helpers shared across providers ----

# District name -> approximate centre (WGS-84)
DISTRICT_CENTRES: dict[str, tuple[float, float]] = {
    "Da'an": (25.0268, 121.5437),
    "Zhongzheng": (25.0323, 121.5185),
    "Wanhua": (25.0340, 121.4997),
    "Zhongshan": (25.0640, 121.5264),
    "Xinyi": (25.0330, 121.5654),
    "Shilin": (25.0930, 121.5252),
    "Beitou": (25.1320, 121.5010),
    "Songshan": (25.0497, 121.5579),
    "Datong": (25.0632, 121.5131),
    "Neihu": (25.0830, 121.5880),
    "Wenshan": (24.9890, 121.5700),
    "Nangang": (25.0550, 121.6060),
}


def district_centre(district: str) -> tuple[float, float]:
    return DISTRICT_CENTRES.get(district, (25.0330, 121.5654))


def stable_venue_id(source: str, external_id: str) -> str:
    """Deterministic venue_id so the same place always deduplicates."""
    raw = f"{source}:{external_id}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def map_cost_level(price_level: int | None) -> str:
    if price_level is None or price_level <= 1:
        return "low"
    if price_level <= 2:
        return "medium"
    return "high"


INTEREST_TO_GOOGLE_TYPE: dict[str, str] = {
    "food": "restaurant",
    "cafe": "cafe",
    "culture": "museum",
    "history": "museum",
    "art": "art_gallery",
    "shopping": "shopping_mall",
    "nature": "park",
    "nightlife": "night_club",
    "temple": "hindu_temple",
    "sports": "gym",
}


GOOGLE_TYPE_TO_CATEGORY: dict[str, str] = {
    "restaurant": "restaurant",
    "cafe": "cafe",
    "museum": "museum",
    "art_gallery": "gallery",
    "shopping_mall": "shopping",
    "park": "park",
    "night_club": "nightlife",
    "hindu_temple": "temple",
    "tourist_attraction": "landmark",
    "gym": "activity",
    "store": "shopping",
    "bar": "nightlife",
    "bakery": "cafe",
    "book_store": "shopping",
    "spa": "activity",
}

# Google place types that are never tourist attractions — filtered out before ingestion.
BLOCKED_PLACE_TYPES: frozenset[str] = frozenset({
    "real_estate_agency", "insurance_agency", "lawyer", "accounting",
    "doctor", "dentist", "hospital", "pharmacy", "veterinary_care",
    "bank", "atm",
    "gas_station", "car_wash", "car_repair", "car_dealer",
    "storage", "moving_company",
    "funeral_home", "cemetery",
})
