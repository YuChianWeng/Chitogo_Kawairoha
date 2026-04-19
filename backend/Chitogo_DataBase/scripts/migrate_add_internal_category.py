from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.models  # noqa: F401
from app.db import engine
from app.services.category import map_category


def has_internal_category_column(conn) -> bool:
    result = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'places' AND column_name = 'internal_category'
            """
        )
    )
    return result.scalar_one_or_none() is not None


def ensure_internal_category_column(conn) -> bool:
    if has_internal_category_column(conn):
        return False

    conn.execute(text("ALTER TABLE places ADD COLUMN internal_category VARCHAR(32)"))
    return True


def ensure_internal_category_index(conn) -> None:
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_places_internal_category "
            "ON places (internal_category)"
        )
    )


def backfill_internal_category(conn) -> int:
    rows = conn.execute(
        text(
            """
            SELECT id, primary_type, types_json
            FROM places
            WHERE internal_category IS NULL
            ORDER BY id
            """
        )
    ).mappings()

    updated = 0
    for row in rows:
        conn.execute(
            text(
                """
                UPDATE places
                SET internal_category = :internal_category
                WHERE id = :place_id
                """
            ),
            {
                "internal_category": map_category(
                    row["primary_type"],
                    row["types_json"],
                ),
                "place_id": row["id"],
            },
        )
        updated += 1

    return updated


def enforce_internal_category_constraints(conn) -> None:
    conn.execute(
        text("ALTER TABLE places ALTER COLUMN internal_category SET DEFAULT 'other'")
    )
    conn.execute(
        text("ALTER TABLE places ALTER COLUMN internal_category SET NOT NULL")
    )


def count_null_internal_categories(conn) -> int:
    return int(
        conn.execute(
            text("SELECT COUNT(*) FROM places WHERE internal_category IS NULL")
        ).scalar_one()
    )


def migrate() -> int:
    with engine.begin() as conn:
        created_column = ensure_internal_category_column(conn)
        ensure_internal_category_index(conn)
        updated_rows = backfill_internal_category(conn)
        null_count = count_null_internal_categories(conn)
        if null_count != 0:
            raise RuntimeError(
                f"Backfill incomplete: {null_count} places still have NULL internal_category"
            )
        enforce_internal_category_constraints(conn)

    print(
        "internal_category migration complete: "
        f"column_created={created_column}, rows_backfilled={updated_rows}, null_rows=0"
    )
    return updated_rows


def main() -> int:
    migrate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
