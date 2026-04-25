from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class LegalLodgingOut(BaseModel):
    license_no: str
    name: str
    lodging_category: str
    district: str | None = None
    address: str | None = None
    phone: str | None = None
    room_count: int | None = None
    has_hot_spring: bool
    approved_date: date | None = None
    place_id: int | None = None
    matched_by: str | None = None

    model_config = {"from_attributes": True}


class LodgingLegalStatusResponse(BaseModel):
    is_legal: bool
    lodging: LegalLodgingOut | None = None
    # 'exact' when matched by license_no/place_id; 'fuzzy' when matched by name search
    match_type: str | None = None
    # similarity score 0-1 when match_type='fuzzy'
    confidence: float | None = None


class LodgingCandidateItem(BaseModel):
    lodging: LegalLodgingOut
    confidence: float


class LodgingCandidatesResponse(BaseModel):
    items: list[LodgingCandidateItem]


class LodgingCheckQuery(BaseModel):
    name: str
    phone: str | None = None
    district: str | None = None
