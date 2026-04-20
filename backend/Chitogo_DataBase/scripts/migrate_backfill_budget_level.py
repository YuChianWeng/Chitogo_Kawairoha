from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import engine


PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE": "PRICE_LEVEL_FREE",
    "PRICE_LEVEL_INEXPENSIVE": "INEXPENSIVE",
    "PRICE_LEVEL_MODERATE": "MODERATE",
    "PRICE_LEVEL_EXPENSIVE": "EXPENSIVE",
    "PRICE_LEVEL_VERY_EXPENSIVE": "VERY_EXPENSIVE",
}


def backfill_budget_level(conn) -> tuple[int, int]:
    rows = conn.execute(
        text(
            """
            SELECT id, price_level
            FROM places
            WHERE price_level IS NOT NULL
            ORDER BY id
            """
        )
    ).mappings()

    updated = 0
    skipped = 0
    for row in rows:
        budget = PRICE_LEVEL_MAP.get(row["price_level"])
        if budget is None:
            skipped += 1
            continue
        conn.execute(
            text("UPDATE places SET budget_level = :budget WHERE id = :id"),
            {"budget": budget, "id": row["id"]},
        )
        updated += 1

    return updated, skipped


def print_summary(conn) -> None:
    rows = conn.execute(
        text(
            """
            SELECT budget_level, COUNT(*) AS cnt
            FROM places
            WHERE budget_level IS NOT NULL
            GROUP BY budget_level
            ORDER BY budget_level
            """
        )
    ).mappings()
    print("budget_level distribution after backfill:")
    for row in rows:
        print(f"  {row['budget_level']}: {row['cnt']}")

    null_count = conn.execute(
        text("SELECT COUNT(*) FROM places WHERE budget_level IS NULL")
    ).scalar_one()
    print(f"  (still NULL): {null_count}")


def main() -> int:
    with engine.begin() as conn:
        updated, skipped = backfill_budget_level(conn)
        print(f"backfill complete: updated={updated}, skipped_unknown_price_level={skipped}")
        print_summary(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
