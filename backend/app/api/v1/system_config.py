from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.core.security import get_current_user
from backend.app.models.system_config import SystemConfig
from backend.app.models.user import User
from backend.app.schemas.system_config import (
    SystemConfigResponse,
    SystemConfigUpdate,
)

router = APIRouter(prefix="/system-config", tags=["system-config"])


@router.get("", response_model=List[SystemConfigResponse])
async def list_system_config(
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    result = await session.execute(select(SystemConfig))
    configs = result.scalars().all()
    return [SystemConfigResponse.model_validate(c) for c in configs]


@router.put("/{key}", response_model=SystemConfigResponse)
async def update_system_config(
    key: str,
    data: SystemConfigUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    existing = await session.get(SystemConfig, key)

    if existing:
        existing.value = data.value
        existing.updated_by = current_user.id
        config = existing
    else:
        config = SystemConfig(
            key=key,
            value=data.value,
            updated_by=current_user.id,
        )
        session.add(config)

    await session.flush()
    await session.refresh(config)
    return config
