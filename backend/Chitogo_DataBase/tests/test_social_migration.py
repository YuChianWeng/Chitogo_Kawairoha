import unittest
from unittest.mock import patch

from app.models import Place, PlaceSocialMention
from scripts import migrate_add_social_tables


class FakeResult:
    def __init__(self, scalar_value=None):
        self.scalar_value = scalar_value

    def scalar_one_or_none(self):
        return self.scalar_value

    def scalar_one(self):
        return self.scalar_value


class FakeConnection:
    def __init__(self):
        self.tables = {"places"}
        self.place_columns = {"id", "google_place_id"}
        self.constraints = set()
        self.indexes = set()
        self.mention_count_null_rows = 3
        self.column_defaults = {}
        self.column_nullable = {}
        self.default_set = False
        self.not_null_set = False

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}

        if "FROM information_schema.tables" in sql:
            table_name = params["table_name"]
            return FakeResult(table_name if table_name in self.tables else None)

        if "FROM information_schema.columns" in sql:
            table_name = params["table_name"]
            column_name = params["column_name"]
            key = (table_name, column_name)
            column_exists = table_name == "places" and column_name in self.place_columns

            if "SELECT column_default" in sql:
                return FakeResult(self.column_defaults.get(key))

            if "SELECT is_nullable" in sql:
                nullable = self.column_nullable.get(key)
                if not column_exists:
                    return FakeResult(None)
                return FakeResult("YES" if nullable else "NO")

            if column_exists:
                return FakeResult(column_name)
            return FakeResult(None)

        if "FROM information_schema.table_constraints" in sql:
            constraint_name = params["constraint_name"]
            return FakeResult(
                constraint_name if constraint_name in self.constraints else None
            )

        if "FROM pg_indexes" in sql:
            index_name = params["index_name"]
            return FakeResult(index_name if index_name in self.indexes else None)

        if "CREATE TABLE place_social_mentions" in sql:
            self.tables.add("place_social_mentions")
            self.constraints.add(
                "uq_place_social_mentions_platform_external_id"
            )
            return FakeResult()

        if "ALTER TABLE place_social_mentions" in sql and "ADD CONSTRAINT" in sql:
            self.constraints.add("uq_place_social_mentions_platform_external_id")
            return FakeResult()

        if "CREATE INDEX IF NOT EXISTS ix_social_mentions_place_id" in sql:
            self.indexes.add("ix_social_mentions_place_id")
            return FakeResult()

        if "CREATE INDEX IF NOT EXISTS ix_social_mentions_platform" in sql:
            self.indexes.add("ix_social_mentions_platform")
            return FakeResult()

        if "ALTER TABLE places ADD COLUMN vibe_tags JSONB" in sql:
            self.place_columns.add("vibe_tags")
            self.column_defaults[("places", "vibe_tags")] = None
            self.column_nullable[("places", "vibe_tags")] = True
            return FakeResult()

        if "ALTER TABLE places ADD COLUMN mention_count INTEGER" in sql:
            self.place_columns.add("mention_count")
            self.column_defaults[("places", "mention_count")] = None
            self.column_nullable[("places", "mention_count")] = True
            return FakeResult()

        if "SELECT COUNT(*) FROM places WHERE mention_count IS NULL" in sql:
            return FakeResult(self.mention_count_null_rows)

        if "UPDATE places SET mention_count = 0 WHERE mention_count IS NULL" in sql:
            self.mention_count_null_rows = 0
            return FakeResult()

        if "ALTER TABLE places ALTER COLUMN mention_count SET DEFAULT 0" in sql:
            self.default_set = True
            self.column_defaults[("places", "mention_count")] = "0"
            return FakeResult()

        if "ALTER TABLE places ALTER COLUMN mention_count SET NOT NULL" in sql:
            self.not_null_set = True
            self.column_nullable[("places", "mention_count")] = False
            return FakeResult()

        if "ALTER TABLE places ADD COLUMN sentiment_score NUMERIC(3,2)" in sql:
            self.place_columns.add("sentiment_score")
            self.column_defaults[("places", "sentiment_score")] = None
            self.column_nullable[("places", "sentiment_score")] = True
            return FakeResult()

        if "CREATE INDEX IF NOT EXISTS ix_places_mention_count" in sql:
            self.indexes.add("ix_places_mention_count")
            return FakeResult()

        raise AssertionError(f"Unexpected SQL: {sql}")


class FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return FakeBegin(self.conn)


class SocialSchemaModelTests(unittest.TestCase):
    def test_place_model_has_social_summary_fields_and_relationship(self):
        self.assertIn("vibe_tags", Place.__table__.columns)
        self.assertIn("mention_count", Place.__table__.columns)
        self.assertIn("sentiment_score", Place.__table__.columns)
        self.assertIn("social_mentions", Place.__mapper__.relationships)

    def test_place_social_mention_model_has_expected_constraint_and_relationship(self):
        self.assertEqual(PlaceSocialMention.__tablename__, "place_social_mentions")
        self.assertIn("place", PlaceSocialMention.__mapper__.relationships)
        constraint_names = {
            constraint.name
            for constraint in PlaceSocialMention.__table__.constraints
            if constraint.name
        }
        self.assertIn(
            "uq_place_social_mentions_platform_external_id", constraint_names
        )


class SocialMigrationTests(unittest.TestCase):
    def test_migration_creates_schema_and_backfills_mention_count(self):
        conn = FakeConnection()

        with patch.object(migrate_add_social_tables, "get_engine", return_value=FakeEngine(conn)):
            summary = migrate_add_social_tables.migrate()

        self.assertTrue(summary["social_table_created"])
        self.assertFalse(summary["social_constraint_patched"])
        self.assertTrue(summary["social_place_index_created"])
        self.assertTrue(summary["social_platform_index_created"])
        self.assertTrue(summary["vibe_tags_column_created"])
        self.assertTrue(summary["mention_count_column_created"])
        self.assertEqual(summary["mention_count_rows_backfilled"], 3)
        self.assertTrue(summary["mention_count_constraints_enforced"])
        self.assertTrue(summary["sentiment_score_column_created"])
        self.assertTrue(summary["mention_count_index_created"])
        self.assertIn("ix_social_mentions_place_id", conn.indexes)
        self.assertIn("ix_social_mentions_platform", conn.indexes)
        self.assertIn("ix_places_mention_count", conn.indexes)
        self.assertTrue(conn.default_set)
        self.assertTrue(conn.not_null_set)

    def test_migration_is_idempotent_when_schema_already_exists(self):
        conn = FakeConnection()
        conn.tables.add("place_social_mentions")
        conn.place_columns.update({"vibe_tags", "mention_count", "sentiment_score"})
        conn.constraints.add("uq_place_social_mentions_platform_external_id")
        conn.indexes.update(
            {
                "ix_social_mentions_place_id",
                "ix_social_mentions_platform",
                "ix_places_mention_count",
            }
        )
        conn.mention_count_null_rows = 0
        conn.column_defaults[("places", "mention_count")] = "0"
        conn.column_nullable[("places", "mention_count")] = False

        with patch.object(migrate_add_social_tables, "get_engine", return_value=FakeEngine(conn)):
            summary = migrate_add_social_tables.migrate()

        self.assertFalse(summary["social_table_created"])
        self.assertFalse(summary["social_constraint_patched"])
        self.assertFalse(summary["social_place_index_created"])
        self.assertFalse(summary["social_platform_index_created"])
        self.assertFalse(summary["vibe_tags_column_created"])
        self.assertFalse(summary["mention_count_column_created"])
        self.assertEqual(summary["mention_count_rows_backfilled"], 0)
        self.assertFalse(summary["mention_count_constraints_enforced"])
        self.assertFalse(summary["sentiment_score_column_created"])
        self.assertFalse(summary["mention_count_index_created"])
        self.assertFalse(conn.default_set)
        self.assertFalse(conn.not_null_set)

    def test_migration_repairs_partial_schema_when_index_and_constraint_state_drift(self):
        conn = FakeConnection()
        conn.tables.add("place_social_mentions")
        conn.place_columns.update({"vibe_tags", "mention_count"})
        conn.constraints.add("uq_place_social_mentions_platform_external_id")
        conn.column_defaults[("places", "mention_count")] = None
        conn.column_nullable[("places", "mention_count")] = True
        conn.mention_count_null_rows = 0

        with patch.object(migrate_add_social_tables, "get_engine", return_value=FakeEngine(conn)):
            summary = migrate_add_social_tables.migrate()

        self.assertFalse(summary["social_table_created"])
        self.assertFalse(summary["social_constraint_patched"])
        self.assertTrue(summary["social_place_index_created"])
        self.assertTrue(summary["social_platform_index_created"])
        self.assertFalse(summary["vibe_tags_column_created"])
        self.assertFalse(summary["mention_count_column_created"])
        self.assertEqual(summary["mention_count_rows_backfilled"], 0)
        self.assertTrue(summary["mention_count_constraints_enforced"])
        self.assertTrue(summary["sentiment_score_column_created"])
        self.assertTrue(summary["mention_count_index_created"])
        self.assertIn("ix_social_mentions_place_id", conn.indexes)
        self.assertIn("ix_social_mentions_platform", conn.indexes)
        self.assertIn("ix_places_mention_count", conn.indexes)
        self.assertEqual(conn.column_defaults[("places", "mention_count")], "0")
        self.assertFalse(conn.column_nullable[("places", "mention_count")])


if __name__ == "__main__":
    unittest.main()
