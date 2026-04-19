from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.place import Place


class PlaceFeatures(Base):
    __tablename__ = "place_features"

    place_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("places.id"), primary_key=True
    )
    couple_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    family_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    photo_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    food_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    culture_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    rainy_day_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    crowd_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    transport_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    hidden_gem_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    feature_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    place: Mapped["Place"] = relationship("Place", back_populates="features")
