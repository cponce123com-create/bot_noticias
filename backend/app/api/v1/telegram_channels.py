from __future__ import annotations

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

router = APIRouter(prefix="/telegram-channels", tags=["telegram-channels"])


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
    raw = data.channel_id.strip()
    try:
        chat_id = int(raw)
    except ValueError:
        if raw.startswith("@"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usa el ID numérico del canal (negativo para canales públicos), no el @username. "
                        "Ejemplo: -1001234567890",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"channel_id inválido: '{raw}'. Debe ser un número entero o un @username.",
        )

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
