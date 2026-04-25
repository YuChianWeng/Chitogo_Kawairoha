"""
Import government-registered lodging list from an ODS file into legal_lodgings.

Usage:
    python scripts/import_legal_lodgings.py <path/to/旅宿列表匯出.ods>

Matching strategy (in priority order):
  1. phone  — normalize both sides to last-8 digits, exact match
  2. website — normalize URL (strip protocol / www / trailing slash), exact match
  3. name   — difflib ratio >= 0.80 with district match, then retry without district

Run migrate_add_legal_lodgings.py first to create the table.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from odf.opendocument import load
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
except ModuleNotFoundError as exc:
    print(f"Missing dependency: {exc}. Install odfpy:  pip install odfpy", file=sys.stderr)
    raise SystemExit(1)

from app.db import SessionLocal
from app.models.legal_lodging import LegalLodging
from app.models.place import Place

_DIGIT_RE = re.compile(r"\D")
_PROTO_RE = re.compile(r"^https?://", re.IGNORECASE)
_WWW_RE = re.compile(r"^www\.", re.IGNORECASE)
_IMPORT_FUZZY_THRESHOLD = 0.80  # stricter than query-time threshold


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _norm_phone(phone: str) -> str:
    digits = _DIGIT_RE.sub("", phone)
    return digits[-8:] if len(digits) >= 8 else digits


def _norm_url(url: str) -> str:
    u = _PROTO_RE.sub("", url.strip().lower())
    u = _WWW_RE.sub("", u)
    return u.rstrip("/")


def _name_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()


# ---------------------------------------------------------------------------
# ODS reading
# ---------------------------------------------------------------------------

def _cell_text(cell) -> str:
    ps = cell.getElementsByType(P)
    return "".join(str(p) for p in ps) if ps else ""


def _expand_row(row) -> list[str]:
    """Expand repeated-column cells into a flat list."""
    values: list[str] = []
    for cell in row.getElementsByType(TableCell):
        repeat = cell.getAttribute("numbercolumnsrepeated")
        val = _cell_text(cell)
        count = int(repeat) if repeat else 1
        values.extend([val] * min(count, 3))
    return values


def parse_ods(ods_path: Path) -> list[dict]:
    doc = load(str(ods_path))
    sheet = doc.spreadsheet.getElementsByType(Table)[0]
    rows = sheet.getElementsByType(TableRow)
    records = []
    for row in rows[1:]:  # skip header
        v = _expand_row(row)
        if len(v) < 15 or not any(x.strip() for x in v):
            continue
        phone_raw = v[10].strip()
        records.append(
            {
                "approved_date": _parse_date(v[0].strip()),
                "license_no": v[1].strip(),
                "lodging_category": v[2].strip(),
                "name": v[5].strip(),
                "city": v[6].strip(),
                "district": v[7].strip() or None,
                "postal_code": v[8].strip() or None,
                "address": v[9].strip() or None,
                "phone": phone_raw if phone_raw not in ("-", "") else None,
                "room_count": _parse_int(v[12].strip()),
                "email": v[13].strip() or None,
                "website": v[14].strip() or None,
                "has_hot_spring": v[4].strip() == "是",
            }
        )
    return records


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_int(s: str) -> int | None:
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Matching against places table
# ---------------------------------------------------------------------------

def _build_phone_index(session) -> dict[str, int]:
    """phone_8digits → place.id"""
    index: dict[str, int] = {}
    for pid, phone in session.query(Place.id, Place.national_phone_number).filter(
        Place.national_phone_number.isnot(None)
    ):
        key = _norm_phone(phone)
        if key:
            index[key] = pid
    return index


def _build_url_index(session) -> dict[str, int]:
    """normalized_url → place.id"""
    index: dict[str, int] = {}
    for pid, url in session.query(Place.id, Place.website_uri).filter(
        Place.website_uri.isnot(None)
    ):
        key = _norm_url(url)
        if key:
            index[key] = pid
    return index


def _build_name_candidates(session) -> list[tuple[int, str, str | None]]:
    """[(place.id, display_name, district)]"""
    return [
        (pid, name or "", district)
        for pid, name, district in session.query(
            Place.id, Place.display_name, Place.district
        ).filter(Place.internal_category == "lodging")
    ]


def _find_place(
    rec: dict,
    phone_index: dict[str, int],
    url_index: dict[str, int],
    name_candidates: list[tuple[int, str, str | None]],
) -> tuple[int | None, str | None]:
    """Return (place_id, matched_by) or (None, None)."""
    # 1. phone
    if rec["phone"]:
        key = _norm_phone(rec["phone"])
        if key and key in phone_index:
            return phone_index[key], "phone"

    # 2. website
    if rec["website"]:
        key = _norm_url(rec["website"])
        if key and key in url_index:
            return url_index[key], "website"

    # 3. name fuzzy (district-scoped first)
    best_id, best_score = None, 0.0
    for pid, pname, pdistrict in name_candidates:
        if rec["district"] and pdistrict and rec["district"] != pdistrict:
            continue
        score = _name_sim(rec["name"], pname)
        if score > best_score:
            best_score, best_id = score, pid

    if best_id is not None and best_score >= _IMPORT_FUZZY_THRESHOLD:
        return best_id, "name"

    return None, None


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def import_lodgings(ods_path: Path, *, dry_run: bool = False) -> dict:
    records = parse_ods(ods_path)
    print(f"Parsed {len(records)} records from ODS")

    session = SessionLocal()
    try:
        phone_index = _build_phone_index(session)
        url_index = _build_url_index(session)
        name_candidates = _build_name_candidates(session)
        print(
            f"Place indexes built: {len(phone_index)} phone, "
            f"{len(url_index)} url, {len(name_candidates)} name candidates"
        )

        inserted = updated = skipped = matched = unmatched = 0
        for rec in records:
            if not rec["license_no"]:
                skipped += 1
                continue

            place_id, matched_by = _find_place(rec, phone_index, url_index, name_candidates)
            if place_id is not None:
                matched += 1
            else:
                unmatched += 1

            existing = (
                session.query(LegalLodging)
                .filter(LegalLodging.license_no == rec["license_no"])
                .first()
            )
            if existing is not None:
                # update place_id if we now have a better match
                if place_id is not None and existing.place_id is None:
                    if not dry_run:
                        existing.place_id = place_id
                        existing.matched_by = matched_by
                updated += 1
                continue

            if not dry_run:
                row = LegalLodging(
                    license_no=rec["license_no"],
                    name=rec["name"],
                    lodging_category=rec["lodging_category"],
                    district=rec["district"],
                    postal_code=rec["postal_code"],
                    address=rec["address"],
                    phone=rec["phone"],
                    room_count=rec["room_count"],
                    email=rec["email"],
                    website=rec["website"],
                    has_hot_spring=rec["has_hot_spring"],
                    approved_date=rec["approved_date"],
                    place_id=place_id,
                    matched_by=matched_by,
                )
                session.add(row)
            inserted += 1

        if not dry_run:
            session.commit()

    finally:
        session.close()

    summary = {
        "total": len(records),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "matched_to_place": matched,
        "unmatched": unmatched,
        "dry_run": dry_run,
    }
    print(
        "import complete: "
        + ", ".join(f"{k}={v}" for k, v in summary.items())
    )
    return summary


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Import legal lodgings from ODS")
    parser.add_argument("ods_file", help="Path to 旅宿列表匯出.ods")
    parser.add_argument("--dry-run", action="store_true", help="Parse and match without writing")
    args = parser.parse_args()

    ods_path = Path(args.ods_file)
    if not ods_path.is_file():
        print(f"File not found: {ods_path}", file=sys.stderr)
        return 1

    import_lodgings(ods_path, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
