from __future__ import annotations

import re

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def cjk_character_count(message: str) -> int:
    """Count CJK ideographs in a message."""
    return len(_CJK_PATTERN.findall(message))


def detect_language_hint(message: str) -> str:
    """Return a lightweight language hint for prompts and preference extraction."""
    stripped = message.strip()
    if not stripped:
        return "en"

    cjk_count = cjk_character_count(stripped)
    alnum_count = sum(character.isalnum() for character in stripped)
    if cjk_count >= 2 and (alnum_count == 0 or cjk_count / max(alnum_count, 1) >= 0.2):
        return "zh-TW"
    return "en"


__all__ = ["cjk_character_count", "detect_language_hint"]
