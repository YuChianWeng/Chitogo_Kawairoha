from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.place import Place


class PlaceSocialMention(Base):
    __tablename__ = "place_social_mentions"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "external_id",
            name="uq_place_social_mentions_platform_external_id",
        ),
        Index("ix_social_mentions_place_id", "place_id"),
        Index("ix_social_mentions_platform", "platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("places.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    crowdedness: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    vibe_tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    place: Mapped["Place"] = relationship("Place", back_populates="social_mentions")
