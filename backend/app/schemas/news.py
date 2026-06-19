from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class NewsResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    external_id: Optional[str]
    url: Optional[str]
    original_title: Optional[str]
    original_summary: Optional[str]
    title: Optional[str]
    summary: Optional[str]
    content: Optional[str] = None
    author: Optional[str]
    hashtags: Optional[List[str]]
    category_id: Optional[int]
    category_confidence: Optional[float]
    is_clickbait: bool
    is_spam: bool
    sentiment: Optional[str]
    images: Any
    videos: Any
    published_at: Optional[datetime]
    fetched_at: datetime
    language: str
    status: str
    published_to_tg: Optional[List[int]]
    telegram_msg_ids: Optional[List[int]]
    duplicate_of: Optional[uuid.UUID]
    similarity_score: Optional[float]
    created_at: datetime
    source_name: Optional[str] = None
    category_name: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        data = super().model_validate(obj, **kwargs)
        if obj.source:
            data.source_name = obj.source.name if hasattr(obj.source, "name") else str(obj.source)
        if obj.category:
            data.category_name = obj.category.name if hasattr(obj.category, "name") else str(obj.category)
        if not data.content and obj.body:
            data.content = obj.body
        return data


class NewsListResponse(BaseModel):
    total: int
    items: List[NewsResponse]


class NewsApproveRequest(BaseModel):
    action: str = "approve"  # approve, reject, edit
    title: Optional[str] = None
    summary: Optional[str] = None
    category_id: Optional[int] = None
    notes: Optional[str] = None
