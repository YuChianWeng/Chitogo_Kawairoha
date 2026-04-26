"""Migration: add name_zh / name_en columns and backfill from display_name."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.models  # noqa: F401
from app.db import engine

_CJK_RE = re.compile(r'[一-鿿㐀-䶿豈-﫿　-〿]')


def _has_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _ensure_columns(conn) -> tuple[bool, bool]:
    """Add name_zh and name_en columns if they don't exist. Returns (added_zh, added_en)."""
    existing = {
        row[0]
        for row in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'places' AND column_name IN ('name_zh', 'name_en')"
            )
        )
    }
    added_zh = added_en = False
    if "name_zh" not in existing:
        conn.execute(text("ALTER TABLE places ADD COLUMN name_zh VARCHAR(512)"))
        added_zh = True
        print("Added column: name_zh")
    if "name_en" not in existing:
        conn.execute(text("ALTER TABLE places ADD COLUMN name_en VARCHAR(512)"))
        added_en = True
        print("Added column: name_en")
    return added_zh, added_en


def _backfill(conn) -> None:
    rows = conn.execute(
        text("SELECT id, display_name, name_zh, name_en FROM places")
    ).fetchall()

    zh_ids: list[tuple[str, int]] = []
    en_ids: list[tuple[str, int]] = []
    skip = 0

    for place_id, display_name, name_zh, name_en in rows:
        if name_zh is not None or name_en is not None:
            skip += 1
            continue
        if not display_name:
            skip += 1
            continue
        if _has_chinese(display_name):
            zh_ids.append((display_name, place_id))
        else:
            en_ids.append((display_name, place_id))

    print(f"  Chinese names to fill: {len(zh_ids)}")
    print(f"  English names to fill: {len(en_ids)}")
    print(f"  Already filled / skipped: {skip}")

    if zh_ids:
        conn.execute(
            text("UPDATE places SET name_zh = :v WHERE id = :id"),
            [{"v": v, "id": i} for v, i in zh_ids],
        )
    if en_ids:
        conn.execute(
            text("UPDATE places SET name_en = :v WHERE id = :id"),
            [{"v": v, "id": i} for v, i in en_ids],
        )


def main() -> int:
    with engine.begin() as conn:
        _ensure_columns(conn)
        print("Backfilling name_zh / name_en from display_name...")
        _backfill(conn)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
