from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class PublicationLog(Base):
    __tablename__ = "publication_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    telegram_msg_id: Mapped[int] = mapped_column(BIGINT, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    __table_args__ = (
        CheckConstraint(
            status.in_(["pending", "sent", "failed", "deleted"]),
            name="ck_pub_status",
        ),
    )
