from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.place import Place


class PlaceSourceGoogle(Base):
    __tablename__ = "place_source_google"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("places.id"), nullable=True, index=True
    )
    google_place_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    place: Mapped["Place | None"] = relationship(
        "Place", back_populates="source_records"
    )
