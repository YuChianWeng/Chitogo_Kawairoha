from __future__ import annotations

import unittest

from app.orchestration.language import detect_language_hint


class LanguageDetectionTests(unittest.TestCase):
    def test_cjk_heavy_input_maps_to_traditional_chinese_hint(self) -> None:
        self.assertEqual(detect_language_hint("幫我排今晚的台北行程"), "zh-TW")

    def test_non_cjk_input_defaults_to_english_hint(self) -> None:
        self.assertEqual(detect_language_hint("Plan me a Taipei evening walk"), "en")

    def test_mixed_input_with_substantial_cjk_still_maps_to_traditional_chinese_hint(self) -> None:
        self.assertEqual(detect_language_hint("今晚 Taipei 行程"), "zh-TW")
