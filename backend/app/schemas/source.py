from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(
        ..., pattern=r"^(rss|web|telegram_channel|telegram_group|twitter|youtube)$"
    )
    config: dict = Field(default_factory=dict)
    country: Optional[str] = None
    language: str = "es"
    fetch_interval: int = 300
    priority: int = 5
    auto_publish: bool = False
    requires_approval: bool = True
    target_channels: Optional[List[int]] = None


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None
    country: Optional[str] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None
    is_paused: Optional[bool] = None
    fetch_interval: Optional[int] = None
    priority: Optional[int] = None
    auto_publish: Optional[bool] = None
    requires_approval: Optional[bool] = None
    target_channels: Optional[List[int]] = None


class SourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    source_type: str
    config: Any
    country: Optional[str]
    language: str
    is_active: bool
    is_paused: bool
    last_fetched_at: Optional[datetime]
    fetch_interval: int
    error_count: int
    priority: int
    auto_publish: bool
    requires_approval: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    total: int
    items: List[SourceResponse]
