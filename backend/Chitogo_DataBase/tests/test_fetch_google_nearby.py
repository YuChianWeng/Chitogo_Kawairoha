import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_google_nearby.py"
SPEC = importlib.util.spec_from_file_location("fetch_google_nearby", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FetchGoogleNearbyConfigTests(unittest.TestCase):
    def test_config_contains_expected_districts_and_type_groups(self):
        config = MODULE._load_config()

        self.assertEqual(len(config["districts"]), 12)
        self.assertGreaterEqual(len(config["poi_type_groups"]), 6)

        district_names = {entry["district"] for entry in config["districts"]}
        self.assertIn("中正區", district_names)
        self.assertIn("文山區", district_names)

        for district in config["districts"]:
            self.assertGreaterEqual(len(district["seed_points"]), 3)

        group_names = {group["name"] for group in config["poi_type_groups"]}
        self.assertIn("food_specialties", group_names)
        self.assertIn("transport_rail", group_names)
        self.assertIn("secondary_transport", group_names)

    def test_select_district_returns_one_match(self):
        config = MODULE._load_config()

        selected = MODULE._select_districts(config["districts"], "中正區")

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["district"], "中正區")

    def test_build_nearby_request_uses_single_place_type(self):
        seed_point = {
            "name": "test",
            "center": {"latitude": 25.0, "longitude": 121.5},
            "radius": 1200,
        }

        request_payload = MODULE._build_nearby_request(seed_point, "restaurant")

        self.assertEqual(request_payload["includedTypes"], ["restaurant"])
        self.assertEqual(
            request_payload["locationRestriction"]["circle"]["center"]["latitude"], 25.0
        )
        self.assertEqual(
            request_payload["locationRestriction"]["circle"]["radius"], 1200.0
        )

    def test_build_nearby_request_supports_primary_type_mode(self):
        seed_point = {
            "name": "test",
            "center": {"latitude": 25.0, "longitude": 121.5},
            "radius": 900,
        }

        request_payload = MODULE._build_nearby_request_for_mode(
            seed_point, "japanese_restaurant", "includedPrimaryTypes"
        )

        self.assertEqual(request_payload["includedPrimaryTypes"], ["japanese_restaurant"])
        self.assertNotIn("includedTypes", request_payload)
        self.assertEqual(
            request_payload["locationRestriction"]["circle"]["radius"], 900.0
        )

    def test_secondary_transport_is_disabled_by_default(self):
        config = MODULE._load_config()

        enabled_groups = MODULE._enabled_type_groups(
            config["poi_type_groups"], include_secondary_transport=False
        )
        enabled_group_names = {group["name"] for group in enabled_groups}

        self.assertIn("transport_rail", enabled_group_names)
        self.assertNotIn("secondary_transport", enabled_group_names)

    def test_resolve_group_query_specs_includes_primary_types(self):
        group = {
            "name": "food_specialties",
            "includedPrimaryTypes": ["taiwanese_restaurant", "dessert_shop"],
        }

        query_specs = MODULE._resolve_group_query_specs(group)

        self.assertEqual(
            query_specs,
            [
                ("includedPrimaryTypes", "taiwanese_restaurant"),
                ("includedPrimaryTypes", "dessert_shop"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
