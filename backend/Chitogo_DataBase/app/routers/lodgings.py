from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.lodging import (
    LegalLodgingOut,
    LodgingCandidateItem,
    LodgingCandidatesResponse,
    LodgingLegalStatusResponse,
)
from app.services.lodging_search import (
    check_by_place_id,
    search_lodging,
    search_lodging_candidates,
)

router = APIRouter()


@router.get("/places/{place_id}/legal-status", response_model=LodgingLegalStatusResponse)
def get_place_legal_status(place_id: int, db: Session = Depends(get_db)):
    """Check if a place (by DB id) is a registered legal lodging."""
    row = check_by_place_id(db, place_id)
    if row is None:
        return LodgingLegalStatusResponse(is_legal=False)
    return LodgingLegalStatusResponse(
        is_legal=True,
        lodging=LegalLodgingOut.model_validate(row),
        match_type="exact",
        confidence=1.0,
    )


@router.get("/lodgings/check", response_model=LodgingLegalStatusResponse)
def check_lodging_legal_status(
    name: str = Query(..., min_length=1, description="旅宿名稱"),
    phone: str | None = Query(default=None, description="電話（可選）"),
    district: str | None = Query(default=None, description="行政區（可選）"),
    db: Session = Depends(get_db),
):
    """
    Check if a lodging is legally registered by name/phone search.
    Does not require the lodging to exist in the places table.
    """
    row, match_type, confidence = search_lodging(
        db, name=name, phone=phone, district=district
    )
    if row is None:
        return LodgingLegalStatusResponse(is_legal=False)
    return LodgingLegalStatusResponse(
        is_legal=True,
        lodging=LegalLodgingOut.model_validate(row),
        match_type=match_type,
        confidence=confidence,
    )


@router.get("/lodgings/candidates", response_model=LodgingCandidatesResponse)
def get_lodging_candidates(
    name: str = Query(..., min_length=1, description="旅宿名稱（模糊搜尋）"),
    limit: int = Query(default=5, ge=1, le=10, description="最多回傳幾筆"),
    db: Session = Depends(get_db),
):
    """Return top-N lodging candidates sorted by name similarity."""
    results = search_lodging_candidates(db, name=name, limit=limit)
    items = [
        LodgingCandidateItem(
            lodging=LegalLodgingOut.model_validate(row),
            confidence=round(score, 3),
        )
        for row, score in results
    ]
    return LodgingCandidatesResponse(items=items)


@router.get("/lodgings", response_model=list[LegalLodgingOut])
def list_legal_lodgings(
    district: str | None = Query(default=None),
    lodging_category: str | None = Query(default=None),
    has_hot_spring: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List all registered legal lodgings with optional filters."""
    from app.models.legal_lodging import LegalLodging

    q = db.query(LegalLodging)
    if district:
        q = q.filter(LegalLodging.district == district)
    if lodging_category:
        q = q.filter(LegalLodging.lodging_category == lodging_category)
    if has_hot_spring is not None:
        q = q.filter(LegalLodging.has_hot_spring == has_hot_spring)
    return q.order_by(LegalLodging.name).offset(offset).limit(limit).all()
