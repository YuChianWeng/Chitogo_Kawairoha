import unittest

from app.services.social_ingestion import extract_taipei_district


class SocialFallbackDistrictTests(unittest.TestCase):
    def test_returns_none_for_none_address(self):
        district = extract_taipei_district(None)

        self.assertIsNone(district)

    def test_extracts_taipei_district_from_chinese_address(self):
        district = extract_taipei_district("106臺北市大安區杭州南路二段61巷39號")

        self.assertEqual(district, "大安區")

    def test_extracts_taipei_district_from_english_address(self):
        district = extract_taipei_district("No. 1, Renai Rd., Da'an District, Taipei City")

        self.assertEqual(district, "大安區")

    def test_returns_none_for_non_taipei_address(self):
        district = extract_taipei_district("234新北市永和區永和路一段1號")

        self.assertIsNone(district)


if __name__ == "__main__":
    unittest.main()
