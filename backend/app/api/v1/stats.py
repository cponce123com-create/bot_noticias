from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.app.core.database import get_session
from backend.app.core.security import get_current_user
from backend.app.models.news import News
from backend.app.models.source import Source
from backend.app.models.user import User
from backend.app.schemas.stats import StatsResponse

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
async def get_stats(
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    today = date.today()

    total_sources_query = select(func.count(Source.id))
    total_sources = (await session.execute(total_sources_query)).scalar() or 0

    active_sources_query = select(func.count(Source.id)).where(Source.is_active == True)
    active_sources = (await session.execute(active_sources_query)).scalar() or 0

    news_today_query = select(func.count(News.id)).where(
        cast(News.fetched_at, Date) == today
    )
    news_today = (await session.execute(news_today_query)).scalar() or 0

    published_today_query = select(func.count(News.id)).where(
        News.status == "published",
        cast(News.fetched_at, Date) == today,
    )
    published_today = (await session.execute(published_today_query)).scalar() or 0

    news_by_source_query = (
        select(
            Source.name,
            func.count(News.id).label("count"),
        )
        .join(Source, News.source_id == Source.id)
        .group_by(Source.name)
        .order_by(func.count(News.id).desc())
        .limit(10)
    )
    news_by_source_result = await session.execute(news_by_source_query)
    news_by_source = [
        {"name": row[0], "count": row[1]}
        for row in news_by_source_result
    ]

    return StatsResponse(
        total_sources=total_sources,
        active_sources=active_sources,
        news_today=news_today,
        published_today=published_today,
        news_by_source=news_by_source,
    )
