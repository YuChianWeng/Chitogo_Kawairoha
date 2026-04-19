from __future__ import annotations

import unittest

from app.services.category import get_category_metadata
from tests.direct_api_client import DirectApiClient


class CategoriesApiTests(unittest.TestCase):
    def setUp(self):
        self.client = DirectApiClient(session=None)

    def test_categories_returns_mapping_metadata_in_deterministic_order(self):
        response = self.client.get("/api/v1/places/categories")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("categories", body)

        categories = body["categories"]
        self.assertEqual(categories, get_category_metadata())
        self.assertEqual(
            [item["value"] for item in categories],
            [
                "attraction",
                "food",
                "shopping",
                "lodging",
                "transport",
                "nightlife",
                "other",
            ],
        )

        for item in categories:
            self.assertIn("label", item)
            self.assertIn("representative_types", item)
            if item["value"] != "other":
                self.assertTrue(item["representative_types"])


if __name__ == "__main__":
    unittest.main()
