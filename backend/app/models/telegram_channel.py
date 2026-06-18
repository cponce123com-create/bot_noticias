from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import BIGINT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class TelegramChannel(Base):
    __tablename__ = "telegram_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BIGINT, unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=True)
    channel_type: Mapped[str] = mapped_column(
        String(20), default="channel", server_default="channel"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint(
            channel_type.in_(["channel", "group", "supergroup"]),
            name="ck_channel_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<TelegramChannel {self.channel_name or self.chat_id}>"
