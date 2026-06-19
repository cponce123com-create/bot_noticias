from __future__ import annotations

import logging

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.core.security import get_current_user
from backend.app.models.telegram_channel import TelegramChannel
from backend.app.models.user import User
from backend.app.schemas.telegram_channel import (
    TelegramChannelCreate,
    TelegramChannelResponse,
)
from backend.app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram-channels", tags=["telegram-channels"])


async def _resolve_chat_id(raw: str) -> int:
    """Convierte un @username a chat_id numerico usando la API de Telegram."""
    if raw.startswith("@"):
        username = raw.lstrip("@")
        token = settings.telegram_bot_token
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede resolver @username: TELEGRAM_BOT_TOKEN no está configurado. "
                        "Configúralo o usa el ID numérico del canal directamente.",
            )
        try:
            import httpx
            url = f"https://api.telegram.org/bot{token}/getChat"
            resp = httpx.post(url, json={"chat_id": f"@{username}"}, timeout=10)
            data = resp.json()
            if not data.get("ok"):
                error_desc = data.get("description", "error desconocido")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No se pudo encontrar el canal @{username}: {error_desc}. "
                            f"Verifica que el bot esté agregado como administrador del canal @{username}.",
                )
            chat_id = data["result"]["id"]
            logger.info("Resuelto @%s → chat_id=%s", username, chat_id)
            return chat_id
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"No se pudo conectar con Telegram para resolver @{username}: {e}",
            )
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{raw}' no es un número válido ni un @username. "
                    "Ingresa el ID numérico del canal (ej: -1001234567890) "
                    "o un @username (el bot debe ser miembro del canal).",
        )


@router.get("", response_model=List[TelegramChannelResponse])
async def list_telegram_channels(
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(TelegramChannel))
    channels = result.scalars().all()
    return [TelegramChannelResponse.model_validate(c) for c in channels]


@router.post("", response_model=TelegramChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_telegram_channel(
    data: TelegramChannelCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    chat_id = await _resolve_chat_id(data.channel_id.strip())

    existing = await session.execute(
        select(TelegramChannel).where(TelegramChannel.chat_id == chat_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un canal con ese chat_id",
        )

    channel = TelegramChannel(
        chat_id=chat_id,
        channel_name=data.name,
        is_active=data.is_active,
    )
    session.add(channel)
    await session.flush()
    await session.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_telegram_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    channel = await session.get(TelegramChannel, channel_id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canal no encontrado",
        )
    await session.delete(channel)
