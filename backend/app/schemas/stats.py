from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel


class StatsResponse(BaseModel):
    total_sources: int
    active_sources: int
    news_today: int
    published_today: int
    news_by_source: List[dict[str, Any]]
