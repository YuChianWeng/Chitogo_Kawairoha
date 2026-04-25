from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.place import Place


class LegalLodging(Base):
    __tablename__ = "legal_lodgings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    license_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    lodging_category: Mapped[str] = mapped_column(String(32), nullable=False)
    district: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    postal_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    room_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    has_hot_spring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    place_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("places.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # how the place_id link was established: 'phone', 'website', 'name', or None
    matched_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    place: Mapped["Place | None"] = relationship("Place", foreign_keys=[place_id])
