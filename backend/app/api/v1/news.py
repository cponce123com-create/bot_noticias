from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.app.core.database import get_session
from backend.app.core.security import get_current_user
from backend.app.models.news import News
from backend.app.models.user import User
from backend.app.schemas.news import (
    NewsApproveRequest,
    NewsListResponse,
    NewsResponse,
)

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=NewsListResponse)
async def list_news(
    status_filter: Optional[str] = Query(None, alias="status"),
    source_id: Optional[uuid.UUID] = Query(None),
    category_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    query = select(News).options(
        joinedload(News.source), joinedload(News.category)
    )
    count_query = select(func.count(News.id))

    if status_filter:
        query = query.where(News.status == status_filter)
        count_query = count_query.where(News.status == status_filter)
    if source_id:
        query = query.where(News.source_id == source_id)
        count_query = count_query.where(News.source_id == source_id)
    if category_id:
        query = query.where(News.category_id == category_id)
        count_query = count_query.where(News.category_id == category_id)

    total = (await session.execute(count_query)).scalar() or 0
    query = query.order_by(desc(News.fetched_at)).offset(
        (page - 1) * page_size
    ).limit(page_size)

    result = await session.execute(query)
    items = result.unique().scalars().all()

    return NewsListResponse(
        total=total,
        items=[NewsResponse.model_validate(n) for n in items],
    )


@router.get("/approval-queue", response_model=NewsListResponse)
async def get_approval_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    query = (
        select(News)
        .options(joinedload(News.source), joinedload(News.category))
        .where(News.status == "pending_approval")
        .order_by(desc(News.fetched_at))
    )
    count_query = select(func.count(News.id)).where(News.status == "pending_approval")

    total = (await session.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    items = result.unique().scalars().all()

    return NewsListResponse(
        total=total,
        items=[NewsResponse.model_validate(n) for n in items],
    )


@router.post("/{news_id}/approve", response_model=NewsResponse)
async def approve_news(
    news_id: uuid.UUID,
    data: Optional[NewsApproveRequest] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    news = await session.get(News, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Noticia no encontrada")

    action = data.action if data else "approve"

    if action == "approve":
        news.status = "published"
        if data and data.title:
            news.title = data.title
        if data and data.summary:
            news.summary = data.summary
        if data and data.category_id:
            news.category_id = data.category_id
    elif action == "reject":
        news.status = "rejected"
    elif action == "edit":
        news.status = "published"
        if data and data.title:
            news.title = data.title
        if data and data.summary:
            news.summary = data.summary
        if data and data.category_id:
            news.category_id = data.category_id
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Accion invalida")

    news.reviewed_by = current_user.id
    if data:
        news.review_notes = data.notes

    await session.flush()
    await session.refresh(news)

    # Publicar en Telegram si fue aprobada (error silencioso)
    if action in ("approve", "edit"):
        try:
            await _publish_news_to_telegram(news, session)
        except Exception:
            pass  # Error silencioso - la noticia ya quedo como publicada en DB

    return news


async def _publish_news_to_telegram(news: News, session: AsyncSession) -> None:
    """Publica una noticia aprobada a los canales de Telegram configurados."""
    logger = logging.getLogger(__name__)
    try:
        from sqlalchemy import select as sql_select
        from backend.app.models.telegram_channel import TelegramChannel

        result = await session.execute(
            sql_select(TelegramChannel).where(TelegramChannel.is_active == True)
        )
        channels = result.scalars().all()

        if not channels:
            logger.info("No hay canales de Telegram configurados para publicar")
            return

        # Cargar source si existe
        from backend.app.models.source import Source
        source = await session.get(Source, news.source_id) if news.source_id else None
        source_name = source.name if source else ""

        # Preparar y publicar
        from workers.publishers.telegram_publisher import PublicationPayload, TelegramPublisher
        from datetime import datetime, timezone

        publisher = TelegramPublisher()

        for channel in channels:
            try:
                payload = PublicationPayload(
                    title=news.title or news.original_title or "",
                    summary=news.summary or news.original_summary,
                    url=news.url,
                    hashtags=news.hashtags or [],
                    category_slug="",
                    images=news.images or [],
                    news_id=str(news.id),
                    published_at=datetime.now(timezone.utc),
                    author=news.author,
                )

                if news.images:
                    msg_id = await publisher.publish_with_image(channel.chat_id, payload)
                else:
                    msg_id = await publisher.publish_text_only(channel.chat_id, payload)

                if msg_id:
                    logger.info(
                        "Publicado en canal %s (msg_id=%s)",
                        channel.channel_name or channel.chat_id,
                        msg_id,
                    )
                else:
                    logger.warning(
                        "No se pudo publicar en canal %s",
                        channel.channel_name or channel.chat_id,
                    )
            except Exception as e:
                logger.error(
                    "Error publicando en canal %s: %s",
                    channel.channel_name or channel.chat_id,
                    e,
                )
    except ImportError as e:
        logger.warning("No se pudo importar TelegramPublisher (puede faltar dependencia): %s", e)
    except ValueError as e:
        logger.warning("TelegramPublisher no disponible: %s", e)
    except Exception as e:
        logger.error("Error inesperado en publicacion Telegram: %s", e)


@router.post("/{news_id}/reject", response_model=NewsResponse)
async def reject_news(
    news_id: uuid.UUID,
    data: Optional[dict] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    news = await session.get(News, news_id)
    if not news:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Noticia no encontrada",
        )

    news.status = "rejected"
    news.reviewed_by = current_user.id
    if data and data.get("reason"):
        news.review_notes = data["reason"]

    await session.flush()
    await session.refresh(news)
    return news
