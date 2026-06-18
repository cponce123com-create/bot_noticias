from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
