"""Unit tests for GooglePlacesProvider quality filtering."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from app.providers.google_places import GooglePlacesProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_place(
    *,
    rating: float | None = 4.5,
    user_count: int | None = 150,
    business_status: str | None = "OPERATIONAL",
    types: list[str] | None = None,
) -> dict:
    place: dict = {
        "id": "abc123",
        "displayName": {"text": "Test Place"},
        "formattedAddress": "1 Test St, Taipei",
        "location": {"latitude": 25.033, "longitude": 121.565},
        "types": types or ["tourist_attraction"],
        "priceLevel": "PRICE_LEVEL_MODERATE",
    }
    if rating is not None:
        place["rating"] = rating
    if user_count is not None:
        place["userRatingCount"] = user_count
    if business_status is not None:
        place["businessStatus"] = business_status
    return place


def _mock_transport(places: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"places": places})
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_place_passes():
    provider = GooglePlacesProvider()
    place = _make_place(rating=4.5, user_count=150, business_status="OPERATIONAL")
    with patch("httpx.AsyncClient", lambda **kw: httpx.Client(transport=_mock_transport([place]))):
        pass  # covered by direct _parse_place call below

    from app.providers.google_places import _parse_place
    result = _parse_place(place)
    assert result is not None
    assert result.name == "Test Place"


@pytest.mark.asyncio
async def test_low_review_count_rejected():
    from app.providers.google_places import _parse_place
    place = _make_place(rating=4.5, user_count=5)
    assert _parse_place(place) is None


@pytest.mark.asyncio
async def test_low_rating_rejected():
    from app.providers.google_places import _parse_place
    place = _make_place(rating=3.0, user_count=200)
    assert _parse_place(place) is None


@pytest.mark.asyncio
async def test_closed_place_rejected():
    from app.providers.google_places import _parse_place
    place = _make_place(business_status="CLOSED_PERMANENTLY")
    assert _parse_place(place) is None


@pytest.mark.asyncio
async def test_temporarily_closed_rejected():
    from app.providers.google_places import _parse_place
    place = _make_place(business_status="CLOSED_TEMPORARILY")
    assert _parse_place(place) is None


@pytest.mark.asyncio
async def test_blocked_type_rejected():
    from app.providers.google_places import _parse_place
    place = _make_place(types=["dentist", "health"])
    assert _parse_place(place) is None


@pytest.mark.asyncio
async def test_blocked_type_mixed_rejected():
    """A place with one blocked type among otherwise valid types is still rejected."""
    from app.providers.google_places import _parse_place
    place = _make_place(types=["tourist_attraction", "insurance_agency"])
    assert _parse_place(place) is None


@pytest.mark.asyncio
async def test_no_rating_data_allowed():
    """Places without any rating data are kept — they may be legitimate new venues."""
    from app.providers.google_places import _parse_place
    place = _make_place(rating=None, user_count=None)
    assert _parse_place(place) is not None


@pytest.mark.asyncio
async def test_missing_business_status_allowed():
    """businessStatus missing from response is treated as operational."""
    from app.providers.google_places import _parse_place
    place = _make_place(business_status=None)
    assert _parse_place(place) is not None
