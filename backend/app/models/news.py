from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, BIGINT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class News(Base):
    __tablename__ = "news"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(500), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=True)
    original_title: Mapped[str] = mapped_column(Text, nullable=True)
    original_summary: Mapped[str] = mapped_column(Text, nullable=True)
    original_body: Mapped[str] = mapped_column(Text, nullable=True)
    author: Mapped[str] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(80), nullable=True)
    summary: Mapped[str] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list] = mapped_column(ARRAY(String), nullable=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )
    category_confidence: Mapped[float] = mapped_column(Float, nullable=True)
    is_clickbait: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_spam: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    sentiment: Mapped[str] = mapped_column(String(20), nullable=True)
    images: Mapped[dict] = mapped_column(JSONB, default=list, server_default="[]")
    videos: Mapped[dict] = mapped_column(JSONB, default=list, server_default="[]")
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    language: Mapped[str] = mapped_column(String(10), default="es", server_default="es")
    status: Mapped[str] = mapped_column(
        String(30), default="ingested", server_default="ingested"
    )
    reviewed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_notes: Mapped[str] = mapped_column(Text, nullable=True)
    published_to_tg: Mapped[list] = mapped_column(ARRAY(BIGINT), nullable=True)
    telegram_msg_ids: Mapped[list] = mapped_column(ARRAY(BIGINT), nullable=True)
    duplicate_of: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news.id"), nullable=True
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    source = relationship("Source", backref="news", lazy="selectin")
    category = relationship("Category", backref="news", lazy="selectin")
    reviewer = relationship(
        "User", backref="reviewed_news", lazy="selectin", foreign_keys=[reviewed_by]
    )
    duplicate = relationship(
        "News", remote_side=[id], backref="duplicates", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            status.in_(
                [
                    "ingested",
                    "duplicate",
                    "cleaned",
                    "classified",
                    "summarized",
                    "media_ready",
                    "pending_approval",
                    "approved",
                    "rejected",
                    "published",
                    "failed",
                ]
            ),
            name="ck_news_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<News {self.title or self.original_title}>"
