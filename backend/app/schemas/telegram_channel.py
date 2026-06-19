from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TelegramChannelCreate(BaseModel):
    name: str
    channel_id: str
    is_active: Optional[bool] = True


class TelegramChannelResponse(BaseModel):
    id: int
    chat_id: int
    channel_name: str
    channel_type: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
