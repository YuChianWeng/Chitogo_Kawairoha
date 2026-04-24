from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SOCIAL_TABLE_NAME = "place_social_mentions"
SOCIAL_UNIQUE_CONSTRAINT = "uq_place_social_mentions_platform_external_id"


def get_engine():
    import app.models  # noqa: F401
    from app.db import engine

    return engine


def has_table(conn, table_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return result.scalar_one_or_none() is not None


def has_column(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none() is not None


def get_column_default(conn, table_name: str, column_name: str) -> str | None:
    result = conn.execute(
        text(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none()


def is_column_nullable(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    nullable = result.scalar_one_or_none()
    return nullable == "YES"


def has_constraint(conn, table_name: str, constraint_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND constraint_name = :constraint_name
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    return result.scalar_one_or_none() is not None


def has_index(conn, index_name: str) -> bool:
    result = conn.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = current_schema() AND indexname = :index_name
            """
        ),
        {"index_name": index_name},
    )
    return result.scalar_one_or_none() is not None


def create_social_mentions_table(conn) -> bool:
    if has_table(conn, SOCIAL_TABLE_NAME):
        return False

    conn.execute(
        text(
            f"""
            CREATE TABLE {SOCIAL_TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                place_id INTEGER NOT NULL REFERENCES places(id) ON DELETE CASCADE,
                platform VARCHAR(32) NOT NULL,
                source_url VARCHAR(1024),
                original_text TEXT,
                sentiment_score NUMERIC(3,2),
                crowdedness NUMERIC(3,2),
                vibe_tags JSONB,
                posted_at TIMESTAMPTZ,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                external_id VARCHAR(128) NOT NULL,
                CONSTRAINT {SOCIAL_UNIQUE_CONSTRAINT} UNIQUE (platform, external_id)
            )
            """
        )
    )
    return True


def ensure_social_mentions_unique_constraint(conn) -> bool:
    if has_constraint(conn, SOCIAL_TABLE_NAME, SOCIAL_UNIQUE_CONSTRAINT):
        return False

    conn.execute(
        text(
            f"""
            ALTER TABLE {SOCIAL_TABLE_NAME}
            ADD CONSTRAINT {SOCIAL_UNIQUE_CONSTRAINT}
            UNIQUE (platform, external_id)
            """
        )
    )
    return True


def ensure_social_mentions_place_index(conn) -> bool:
    if has_index(conn, "ix_social_mentions_place_id"):
        return False

    conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_social_mentions_place_id
            ON {SOCIAL_TABLE_NAME} (place_id)
            """
        )
    )
    return True


def ensure_social_mentions_platform_index(conn) -> bool:
    if has_index(conn, "ix_social_mentions_platform"):
        return False

    conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_social_mentions_platform
            ON {SOCIAL_TABLE_NAME} (platform)
            """
        )
    )
    return True


def ensure_places_vibe_tags_column(conn) -> bool:
    if has_column(conn, "places", "vibe_tags"):
        return False

    conn.execute(text("ALTER TABLE places ADD COLUMN vibe_tags JSONB"))
    return True


def ensure_places_mention_count_column(conn) -> bool:
    if has_column(conn, "places", "mention_count"):
        return False

    conn.execute(text("ALTER TABLE places ADD COLUMN mention_count INTEGER"))
    return True


def count_null_place_mention_counts(conn) -> int:
    return int(
        conn.execute(
            text("SELECT COUNT(*) FROM places WHERE mention_count IS NULL")
        ).scalar_one()
    )


def backfill_place_mention_count(conn) -> int:
    null_count = count_null_place_mention_counts(conn)
    if null_count == 0:
        return 0

    conn.execute(text("UPDATE places SET mention_count = 0 WHERE mention_count IS NULL"))
    return null_count


def ensure_place_mention_count_constraints(conn) -> bool:
    constraints_changed = False

    column_default = get_column_default(conn, "places", "mention_count")
    if column_default is None or "0" not in str(column_default):
        conn.execute(text("ALTER TABLE places ALTER COLUMN mention_count SET DEFAULT 0"))
        constraints_changed = True

    if is_column_nullable(conn, "places", "mention_count"):
        conn.execute(text("ALTER TABLE places ALTER COLUMN mention_count SET NOT NULL"))
        constraints_changed = True

    return constraints_changed


def ensure_places_sentiment_score_column(conn) -> bool:
    if has_column(conn, "places", "sentiment_score"):
        return False

    conn.execute(text("ALTER TABLE places ADD COLUMN sentiment_score NUMERIC(3,2)"))
    return True


def ensure_places_mention_count_index(conn) -> bool:
    if has_index(conn, "ix_places_mention_count"):
        return False

    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_places_mention_count
            ON places (mention_count)
            """
        )
    )
    return True


def migrate() -> dict[str, int | bool]:
    engine = get_engine()

    with engine.begin() as conn:
        social_table_created = create_social_mentions_table(conn)
        social_constraint_patched = ensure_social_mentions_unique_constraint(conn)
        social_place_index_created = ensure_social_mentions_place_index(conn)
        social_platform_index_created = ensure_social_mentions_platform_index(conn)
        vibe_tags_column_created = ensure_places_vibe_tags_column(conn)
        mention_count_column_created = ensure_places_mention_count_column(conn)
        mention_count_rows_backfilled = backfill_place_mention_count(conn)
        mention_count_constraints_enforced = ensure_place_mention_count_constraints(
            conn
        )
        sentiment_score_column_created = ensure_places_sentiment_score_column(conn)
        mention_count_index_created = ensure_places_mention_count_index(conn)

    summary = {
        "social_table_created": social_table_created,
        "social_constraint_patched": social_constraint_patched,
        "social_place_index_created": social_place_index_created,
        "social_platform_index_created": social_platform_index_created,
        "vibe_tags_column_created": vibe_tags_column_created,
        "mention_count_column_created": mention_count_column_created,
        "mention_count_rows_backfilled": mention_count_rows_backfilled,
        "mention_count_constraints_enforced": mention_count_constraints_enforced,
        "sentiment_score_column_created": sentiment_score_column_created,
        "mention_count_index_created": mention_count_index_created,
    }
    print(
        "social schema migration complete: "
        + ", ".join(f"{key}={value}" for key, value in summary.items())
    )
    return summary


def main() -> int:
    migrate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
