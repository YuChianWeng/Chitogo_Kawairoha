from __future__ import annotations

import unittest

from app.orchestration.slots import extract_stop_index


class ReplanSlotExtractionTests(unittest.TestCase):
    def test_extract_stop_index_for_first_stop_in_chinese(self) -> None:
        self.assertEqual(extract_stop_index("請換掉第一站"), 0)

    def test_extract_stop_index_for_second_stop_in_chinese(self) -> None:
        self.assertEqual(extract_stop_index("請換掉第二站"), 1)

    def test_extract_stop_index_for_second_item_variant(self) -> None:
        self.assertEqual(extract_stop_index("可以把第二個換成景點嗎"), 1)

    def test_extract_stop_index_for_second_shop_variant_with_spacing(self) -> None:
        self.assertEqual(extract_stop_index("請把第 二 家換掉"), 1)

    def test_extract_stop_index_for_second_venue_variant_with_spacing(self) -> None:
        self.assertEqual(extract_stop_index("把第  二   間改成公園"), 1)

    def test_extract_stop_index_for_first_stop_in_english(self) -> None:
        self.assertEqual(extract_stop_index("replace the first stop"), 0)

    def test_extract_stop_index_for_third_stop_in_english(self) -> None:
        self.assertEqual(extract_stop_index("replace the third stop with a temple"), 2)

    def test_extract_stop_index_for_numbered_stop_reference(self) -> None:
        self.assertEqual(extract_stop_index("swap stop #3"), 2)

    def test_extract_stop_index_returns_none_without_ordinal(self) -> None:
        self.assertIsNone(extract_stop_index("no ordinal mentioned"))
