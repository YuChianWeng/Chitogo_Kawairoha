from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.place_features import PlaceFeatures
    from app.models.place_source_google import PlaceSourceGoogle


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    google_place_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    primary_type: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    types_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    formatted_address: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    district: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    user_rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    google_maps_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    website_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    national_phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opening_hours_json: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    indoor: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outdoor: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    budget_level: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    internal_category: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, server_default="other"
    )
    trend_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    source_records: Mapped[list["PlaceSourceGoogle"]] = relationship(
        "PlaceSourceGoogle", back_populates="place"
    )
    features: Mapped["PlaceFeatures | None"] = relationship(
        "PlaceFeatures", back_populates="place", uselist=False
    )
