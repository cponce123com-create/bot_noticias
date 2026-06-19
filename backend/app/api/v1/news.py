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

    # Publicar en Telegram si fue aprobada
    if action in ("approve", "edit"):
        try:
            logger.info("Publicando noticia %s en Telegram...", news.id)
            await _publish_to_telegram(news)
            logger.info("Publicacion completada para noticia %s", news.id)
        except Exception as e:
            logger.error("Error publicando noticia %s en Telegram: %s", news.id, e, exc_info=True)

    return news


async def _publish_to_telegram(news: News) -> None:
    """Publica una noticia a los canales de Telegram via API directa."""
    from backend.app.config import settings
    from backend.app.core.database import async_session_factory
    from backend.app.models.telegram_channel import TelegramChannel
    from sqlalchemy import select

    token = settings.telegram_bot_token
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado, no se puede publicar")
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(TelegramChannel).where(TelegramChannel.is_active == True)
        )
        channels = result.scalars().all()

    if not channels:
        logger.info("No hay canales de Telegram activos para publicar")
        return

    # Construir mensaje
    title = news.title or news.original_title or "Sin titulo"
    summary = news.summary or news.original_summary
    url = news.url or ""
    author = news.author or ""

    import html as html_mod

    safe_title = html_mod.escape(title)
    safe_summary = html_mod.escape(summary) if summary else ""
    safe_author = html_mod.escape(author) if author else ""

    lines = [f"\U0001F4F0 <b>{safe_title}</b>"]
    if safe_summary:
        lines.append("")
        lines.append(safe_summary)
    if safe_author:
        lines.append("")
        lines.append(f"\u270F {safe_author}")
    if url:
        escaped_url = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append("")
        lines.append(f"\U0001F517 <a href=\"{escaped_url}\">Leer mas</a>")

    text = "\n".join(lines)

    import httpx

    # Obtener primera imagen si existe
    first_image = None
    if news.images and isinstance(news.images, list):
        for img in news.images:
            if isinstance(img, dict) and img.get("url"):
                first_image = img["url"]
                break

    for channel in channels:
        try:
            if first_image:
                # Enviar foto con caption
                resp = httpx.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    json={
                        "chat_id": channel.chat_id,
                        "photo": first_image,
                        "caption": text,
                        "parse_mode": "HTML",
                    },
                    timeout=30,
                )
            else:
                # Solo texto
                resp = httpx.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": channel.chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=15,
                )
            data = resp.json()
            if data.get("ok"):
                msg_id = data["result"]["message_id"]
                logger.info(
                    "Publicado en canal %s (msg_id=%s)",
                    channel.channel_name or channel.chat_id,
                    msg_id,
                )
            else:
                logger.warning(
                    "Error Telegram en canal %s: %s",
                    channel.channel_name or channel.chat_id,
                    data.get("description", "error desconocido"),
                )
        except Exception as e:
            logger.error(
                "Error publicando en canal %s: %s",
                channel.channel_name or channel.chat_id,
                e,
            )


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
