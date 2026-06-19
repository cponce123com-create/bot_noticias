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

    model_config = {"from_attributes": True}


class NewsListResponse(BaseModel):
    total: int
    items: List[NewsResponse]


class NewsApproveRequest(BaseModel):
    action: str = "approve"  # approve, reject, edit
    title: Optional[str] = None
    summary: Optional[str] = None
    category_id: Optional[int] = None
    notes: Optional[str] = None
