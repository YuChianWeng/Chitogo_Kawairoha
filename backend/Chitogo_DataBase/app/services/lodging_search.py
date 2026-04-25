from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.legal_lodging import LegalLodging

_DIGIT_RE = re.compile(r"\D")
_PROTO_RE = re.compile(r"^https?://", re.IGNORECASE)
_WWW_RE = re.compile(r"^www\.", re.IGNORECASE)

_FUZZY_THRESHOLD = 0.75


def _normalize_phone(phone: str) -> str:
    """Return bare digits; compare by last 8 to handle country-code variants."""
    digits = _DIGIT_RE.sub("", phone)
    return digits[-8:] if len(digits) >= 8 else digits


def _normalize_url(url: str) -> str:
    u = _PROTO_RE.sub("", url.strip().lower())
    u = _WWW_RE.sub("", u)
    return u.rstrip("/")


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()


def check_by_place_id(db: Session, place_id: int) -> LegalLodging | None:
    return db.query(LegalLodging).filter(LegalLodging.place_id == place_id).first()


def search_lodging(
    db: Session,
    *,
    name: str,
    phone: str | None = None,
    district: str | None = None,
) -> tuple[LegalLodging | None, str | None, float | None]:
    """
    Returns (lodging, match_type, confidence).
    match_type: 'phone' | 'website' | 'name' | None
    confidence: 1.0 for phone/website, 0-1 for name fuzzy
    """
    # 1. phone match (most reliable)
    if phone:
        needle = _normalize_phone(phone)
        if needle:
            candidates = db.query(LegalLodging).filter(LegalLodging.phone.isnot(None)).all()
            for row in candidates:
                if _normalize_phone(row.phone or "") == needle:
                    return row, "phone", 1.0

    # 2. name fuzzy match (optionally scoped to district)
    query = db.query(LegalLodging)
    if district:
        query = query.filter(LegalLodging.district == district)
    candidates = query.all()

    best: LegalLodging | None = None
    best_score = 0.0
    for row in candidates:
        score = _name_similarity(name, row.name)
        if score > best_score:
            best_score = score
            best = row

    # retry without district filter if nothing found
    if (best is None or best_score < _FUZZY_THRESHOLD) and district:
        for row in db.query(LegalLodging).all():
            score = _name_similarity(name, row.name)
            if score > best_score:
                best_score = score
                best = row

    if best is not None and best_score >= _FUZZY_THRESHOLD:
        return best, "name", round(best_score, 3)

    return None, None, None
