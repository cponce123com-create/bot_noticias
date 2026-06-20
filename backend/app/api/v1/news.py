from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.app.core.database import get_session
from backend.app.core.security import get_admin_user, get_current_user
from backend.app.models.news import News
from backend.app.models.user import User
from backend.app.schemas.news import (
    NewsApproveRequest,
    NewsListResponse,
    NewsResponse,
    RejectNewsRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=NewsListResponse)
async def list_news(
    status_filter: Optional[str] = Query(None, alias="status"),
    source_id: Optional[uuid.UUID] = Query(None),
    category_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
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
    _current_user: User = Depends(get_admin_user),
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
    current_user: User = Depends(get_admin_user),
):
    news = await session.get(News, news_id)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Noticia no encontrada")

    action = data.action if data else "approve"

    if action == "approve":
        news.status = "approved"
        if data and data.title:
            news.title = data.title
        if data and data.summary:
            news.summary = data.summary
        if data and data.category_id:
            news.category_id = data.category_id
    elif action == "reject":
        news.status = "rejected"
    elif action == "edit":
        news.status = "approved"
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

    # Publicar en Telegram si fue aprobada
    if action in ("approve", "edit"):
        try:
            logger.info("Publicando noticia %s en Telegram...", news.id)
            from workers.publishers.telegram_publisher import publish_single_news
            await publish_single_news(news)
            news.status = "published"
            await session.flush()
            logger.info("Publicacion completada para noticia %s", news.id)
        except Exception as e:
            logger.error("Error publicando noticia %s en Telegram: %s", news.id, e, exc_info=True)
            # Status queda como approved, publish_pending reintentara

    return news


@router.post("/approve-all")
async def approve_all_news(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_admin_user),
):
    """Aprueba todas las noticias pendientes en una sola operacion."""
    result = await session.execute(
        select(News).where(News.status == "pending_approval").limit(50)
    )
    pending = result.scalars().all()

    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay noticias pendientes de aprobacion",
        )

    approved = 0
    for news in pending:
        news.status = "published"
        news.reviewed_by = current_user.id
        approved += 1

    await session.flush()

    # Publicar en Telegram (en paralelo, sin bloquear la respuesta)
    import asyncio

    background_tasks: set[asyncio.Task] = set()

    async def _publish_all():
        from workers.publishers.telegram_publisher import publish_single_news
        for news in pending:
            try:
                await publish_single_news(news)
            except Exception:
                pass

    task = asyncio.ensure_future(_publish_all())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    return {"approved": approved, "total": len(pending)}


@router.post("/scrape-now")
async def scrape_now(
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    """Ejecuta un ciclo de scraping manual inmediato."""
    try:
        from workers.main import scrape_all_sources
        await scrape_all_sources()
        return {"status": "ok", "message": "Scraping completado"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en scraping: {e}",
        )


@router.post("/{news_id}/reject", response_model=NewsResponse)
async def reject_news(
    news_id: uuid.UUID,
    data: Optional[RejectNewsRequest] = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_admin_user),
):
    news = await session.get(News, news_id)
    if not news:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Noticia no encontrada",
        )

    news.status = "rejected"
    news.reviewed_by = current_user.id
    if data and data.reason:
        news.review_notes = data.reason

    await session.flush()
    await session.refresh(news)
    return news
