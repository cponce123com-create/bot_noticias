from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    country: Mapped[str] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="es")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetch_interval: Mapped[int] = mapped_column(Integer, default=300)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    max_errors: Mapped[int] = mapped_column(Integer, default=10)
    cooldown_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=5)
    auto_publish: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    target_channels: Mapped[list] = mapped_column(BIGINT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    creator = relationship("User", backref="sources", lazy="selectin")

    __table_args__ = (
        CheckConstraint(
            source_type.in_(
                [
                    "rss",
                    "web",
                    "telegram_channel",
                    "telegram_group",
                    "twitter",
                    "youtube",
                ]
            ),
            name="ck_source_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<Source {self.name} ({self.source_type})>"
