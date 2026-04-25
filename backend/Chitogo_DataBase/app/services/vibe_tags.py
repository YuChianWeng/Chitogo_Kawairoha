from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.place import Place


@dataclass(frozen=True)
class VibeTagCatalogItem:
    tag: str
    place_count: int
    mention_count: int | None


@dataclass(frozen=True)
class VibeTagCatalogResult:
    items: list[VibeTagCatalogItem]
    limit: int
    scope: dict[str, str | None]


def list_vibe_tags(
    db: Session,
    *,
    district: str | None = None,
    internal_category: str | None = None,
    primary_type: str | None = None,
    limit: int = 50,
) -> VibeTagCatalogResult:
    scope = {
        "district": district,
        "internal_category": internal_category,
        "primary_type": primary_type,
    }
    normalized_limit = max(1, min(limit, 200))

    if _is_postgresql_session(db):
        items = _list_vibe_tags_postgresql(
            db,
            district=district,
            internal_category=internal_category,
            primary_type=primary_type,
            limit=normalized_limit,
        )
    else:
        items = _list_vibe_tags_python(
            db,
            district=district,
            internal_category=internal_category,
            primary_type=primary_type,
            limit=normalized_limit,
        )

    return VibeTagCatalogResult(items=items, limit=normalized_limit, scope=scope)


def _is_postgresql_session(db: Session) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


def _list_vibe_tags_postgresql(
    db: Session,
    *,
    district: str | None,
    internal_category: str | None,
    primary_type: str | None,
    limit: int,
) -> list[VibeTagCatalogItem]:
    query = text(
        """
        WITH scoped_tags AS (
            SELECT DISTINCT
                places.id,
                btrim(tag_values.tag) AS tag,
                COALESCE(places.mention_count, 0) AS mention_count
            FROM places
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE
                    WHEN jsonb_typeof(places.vibe_tags) = 'array' THEN places.vibe_tags
                    ELSE '[]'::jsonb
                END
            ) AS tag_values(tag)
            WHERE places.vibe_tags IS NOT NULL
              AND btrim(tag_values.tag) <> ''
              AND (:district IS NULL OR places.district = :district)
              AND (:internal_category IS NULL OR places.internal_category = :internal_category)
              AND (
                  :primary_type IS NULL
                  OR places.primary_type = :primary_type
                  OR places.types_json @> CAST(:primary_type_json AS jsonb)
              )
        )
        SELECT
            scoped_tags.tag AS tag,
            COUNT(*)::int AS place_count,
            COALESCE(SUM(scoped_tags.mention_count), 0)::int AS mention_count
        FROM scoped_tags
        GROUP BY scoped_tags.tag
        ORDER BY place_count DESC, mention_count DESC, scoped_tags.tag ASC
        LIMIT :limit
        """
    )
    rows = db.execute(
        query,
        {
            "district": district,
            "internal_category": internal_category,
            "primary_type": primary_type,
            "primary_type_json": json.dumps([primary_type]) if primary_type else None,
            "limit": limit,
        },
    )
    return [
        VibeTagCatalogItem(
            tag=str(row._mapping["tag"]),
            place_count=int(row._mapping["place_count"]),
            mention_count=int(row._mapping["mention_count"]),
        )
        for row in rows
    ]


def _list_vibe_tags_python(
    db: Session,
    *,
    district: str | None,
    internal_category: str | None,
    primary_type: str | None,
    limit: int,
) -> list[VibeTagCatalogItem]:
    counts: dict[str, dict[str, int]] = {}

    for place in db.query(Place).all():
        if not _matches_scope(
            place,
            district=district,
            internal_category=internal_category,
            primary_type=primary_type,
        ):
            continue

        mention_count = _safe_int(getattr(place, "mention_count", 0))
        for tag in _normalized_place_tags(getattr(place, "vibe_tags", None)):
            bucket = counts.setdefault(tag, {"place_count": 0, "mention_count": 0})
            bucket["place_count"] += 1
            bucket["mention_count"] += mention_count

    items = [
        VibeTagCatalogItem(
            tag=tag,
            place_count=values["place_count"],
            mention_count=values["mention_count"],
        )
        for tag, values in counts.items()
    ]
    items.sort(
        key=lambda item: (-item.place_count, -int(item.mention_count or 0), item.tag)
    )
    return items[:limit]


def _matches_scope(
    place: Place,
    *,
    district: str | None,
    internal_category: str | None,
    primary_type: str | None,
) -> bool:
    if district is not None and place.district != district:
        return False
    if internal_category is not None and place.internal_category != internal_category:
        return False
    if primary_type is not None:
        if place.primary_type == primary_type:
            return True
        types_json = getattr(place, "types_json", None)
        return isinstance(types_json, list) and primary_type in types_json
    return True


def _normalized_place_tags(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()

    tags: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if tag:
            tags.add(tag)
    return tags


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
