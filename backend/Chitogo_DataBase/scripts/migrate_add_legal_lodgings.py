"""Idempotent migration: create the legal_lodgings table if it does not exist."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TABLE_NAME = "legal_lodgings"


def get_engine():
    import app.models  # noqa: F401 — ensures all models are registered
    from app.db import engine

    return engine


def has_table(conn, table_name: str) -> bool:
    result = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :t"
        ),
        {"t": table_name},
    )
    return result.scalar_one_or_none() is not None


def create_legal_lodgings_table(conn) -> bool:
    if has_table(conn, TABLE_NAME):
        return False

    conn.execute(
        text(
            f"""
            CREATE TABLE {TABLE_NAME} (
                id            SERIAL PRIMARY KEY,
                license_no    VARCHAR(64)  UNIQUE NOT NULL,
                name          VARCHAR(256) NOT NULL,
                lodging_category VARCHAR(32) NOT NULL,
                district      VARCHAR(32),
                postal_code   VARCHAR(8),
                address       VARCHAR(512),
                phone         VARCHAR(32),
                room_count    INTEGER,
                email         VARCHAR(256),
                website       VARCHAR(512),
                has_hot_spring BOOLEAN NOT NULL DEFAULT FALSE,
                approved_date  DATE,
                place_id      INTEGER REFERENCES places(id) ON DELETE SET NULL,
                matched_by    VARCHAR(16),
                created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        text(f"CREATE INDEX IF NOT EXISTS ix_legal_lodgings_name ON {TABLE_NAME} (name)")
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_legal_lodgings_district ON {TABLE_NAME} (district)"
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_legal_lodgings_place_id ON {TABLE_NAME} (place_id)"
        )
    )
    return True


def migrate() -> dict[str, bool]:
    engine = get_engine()
    with engine.begin() as conn:
        table_created = create_legal_lodgings_table(conn)

    summary = {"table_created": table_created}
    print(
        "legal_lodgings migration complete: "
        + ", ".join(f"{k}={v}" for k, v in summary.items())
    )
    return summary


def main() -> int:
    migrate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
