import unittest
from unittest.mock import patch

from app.services.category import budget_rank, map_category
from scripts import migrate_add_internal_category


class CategoryMappingTests(unittest.TestCase):
    def test_primary_type_takes_priority_over_types_json(self):
        self.assertEqual(
            map_category("restaurant", ["museum", "tourist_attraction"]),
            "food",
        )

    def test_types_json_is_used_when_primary_type_is_missing(self):
        self.assertEqual(
            map_category(None, ["point_of_interest", "shopping_mall"]),
            "attraction",
        )

    def test_unmapped_values_fall_back_to_other(self):
        self.assertEqual(map_category("unknown_type", ["another_unknown"]), "other")
        self.assertEqual(map_category(None, None), "other")

    def test_representative_attraction_mapping(self):
        self.assertEqual(map_category("museum", []), "attraction")

    def test_representative_food_mapping(self):
        self.assertEqual(map_category("bakery", []), "food")

    def test_representative_shopping_mapping(self):
        self.assertEqual(map_category("shopping_mall", []), "shopping")

    def test_representative_lodging_mapping(self):
        self.assertEqual(map_category("hotel", []), "lodging")

    def test_representative_transport_mapping(self):
        self.assertEqual(map_category("train_station", []), "transport")

    def test_nightlife_rule_is_deterministic(self):
        self.assertEqual(map_category("bar", ["restaurant"]), "nightlife")
        self.assertEqual(map_category(None, ["pub"]), "nightlife")

    def test_budget_rank_returns_numeric_ordering(self):
        self.assertEqual(budget_rank("MODERATE"), 2)
        self.assertIsNone(budget_rank("UNKNOWN"))


class FakeResult:
    def __init__(self, scalar_value=None, mapping_rows=None):
        self.scalar_value = scalar_value
        self.mapping_rows = mapping_rows or []

    def scalar_one_or_none(self):
        return self.scalar_value

    def scalar_one(self):
        return self.scalar_value

    def mappings(self):
        return self.mapping_rows


class FakeConnection:
    def __init__(self):
        self.column_exists = False
        self.rows = [
            {
                "id": 1,
                "primary_type": "museum",
                "types_json": ["museum", "point_of_interest"],
                "internal_category": None,
            },
            {
                "id": 2,
                "primary_type": None,
                "types_json": ["hotel"],
                "internal_category": None,
            },
            {
                "id": 3,
                "primary_type": "unknown_type",
                "types_json": ["still_unknown"],
                "internal_category": None,
            },
        ]
        self.index_created = False
        self.default_set = False
        self.not_null_set = False

    def execute(self, statement, params=None):
        sql = str(statement)

        if "FROM information_schema.columns" in sql:
            return FakeResult("internal_category" if self.column_exists else None)

        if sql.startswith("ALTER TABLE places ADD COLUMN internal_category"):
            self.column_exists = True
            return FakeResult()

        if sql.startswith("CREATE INDEX IF NOT EXISTS ix_places_internal_category"):
            self.index_created = True
            return FakeResult()

        if "SELECT id, primary_type, types_json" in sql:
            return FakeResult(mapping_rows=[row for row in self.rows if row["internal_category"] is None])

        if "UPDATE places" in sql:
            for row in self.rows:
                if row["id"] == params["place_id"]:
                    row["internal_category"] = params["internal_category"]
                    break
            return FakeResult()

        if "SELECT COUNT(*) FROM places WHERE internal_category IS NULL" in sql:
            null_count = sum(1 for row in self.rows if row["internal_category"] is None)
            return FakeResult(null_count)

        if "ALTER TABLE places ALTER COLUMN internal_category SET DEFAULT 'other'" in sql:
            self.default_set = True
            return FakeResult()

        if "ALTER TABLE places ALTER COLUMN internal_category SET NOT NULL" in sql:
            self.not_null_set = True
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


class MigrationTests(unittest.TestCase):
    def test_migration_backfills_rows_and_enforces_non_null(self):
        conn = FakeConnection()

        with patch.object(
            migrate_add_internal_category,
            "engine",
            FakeEngine(conn),
        ):
            updated_rows = migrate_add_internal_category.migrate()

        self.assertEqual(updated_rows, 3)
        self.assertTrue(conn.column_exists)
        self.assertTrue(conn.index_created)
        self.assertTrue(conn.default_set)
        self.assertTrue(conn.not_null_set)
        self.assertEqual(
            [row["internal_category"] for row in conn.rows],
            ["attraction", "lodging", "other"],
        )

    def test_migration_is_idempotent_when_column_already_exists(self):
        conn = FakeConnection()
        conn.column_exists = True
        conn.rows = []

        with patch.object(
            migrate_add_internal_category,
            "engine",
            FakeEngine(conn),
        ):
            updated_rows = migrate_add_internal_category.migrate()

        self.assertEqual(updated_rows, 0)
        self.assertTrue(conn.index_created)
        self.assertTrue(conn.default_set)
        self.assertTrue(conn.not_null_set)


if __name__ == "__main__":
    unittest.main()
