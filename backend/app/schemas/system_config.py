from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SystemConfigResponse(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SystemConfigUpdate(BaseModel):
    value: Any
