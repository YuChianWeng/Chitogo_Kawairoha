"""Lightweight in-memory TTL cache for provider results."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.models.db import Venue

logger = logging.getLogger(__name__)

CacheKey = str  # e.g. "google:daan:food,cafe"


def make_cache_key(source: str, district: str, interests: list[str]) -> CacheKey:
    tag_part = ",".join(sorted(interests)) if interests else "_all"
    return f"{source}:{district}:{tag_part}"


class _CacheEntry:
    __slots__ = ("venues", "created_at")

    def __init__(self, venues: list[Venue]) -> None:
        self.venues = venues
        self.created_at = time.monotonic()


class TTLCache:
    """Simple in-memory cache with per-entry TTL expiry."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._store: dict[CacheKey, _CacheEntry] = {}
        self._ttl = ttl_seconds

    def get(self, key: CacheKey) -> list[Venue] | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        age = time.monotonic() - entry.created_at
        if age > self._ttl:
            del self._store[key]
            return None
        logger.debug("Cache HIT for %s (age=%.0fs)", key, age)
        return entry.venues

    def put(self, key: CacheKey, venues: list[Venue]) -> None:
        self._store[key] = _CacheEntry(venues)

    def invalidate(self, key: CacheKey) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)
