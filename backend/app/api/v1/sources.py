from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.core.security import get_admin_user
from backend.app.models.source import Source
from backend.app.models.user import User
from backend.app.schemas.source import (
    SourceCreate,
    SourceListResponse,
    SourceResponse,
    SourceUpdate,
)

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=SourceListResponse)
async def list_sources(
    source_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    country: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
):
    query = select(Source)
    count_query = select(func.count(Source.id))

    if source_type:
        query = query.where(Source.source_type == source_type)
        count_query = count_query.where(Source.source_type == source_type)
    if is_active is not None:
        query = query.where(Source.is_active == is_active)
        count_query = count_query.where(Source.is_active == is_active)
    if country:
        query = query.where(Source.country == country)
        count_query = count_query.where(Source.country == country)

    total = (await session.execute(count_query)).scalar() or 0
    query = query.order_by(Source.priority.desc(), Source.name).offset(
        (page - 1) * page_size
    ).limit(page_size)

    result = await session.execute(query)
    items = result.scalars().all()

    return SourceListResponse(
        total=total,
        items=[SourceResponse.model_validate(s) for s in items],
    )


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
):
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuente no encontrada")
    return source


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    data: SourceCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
):
    import ipaddress
    from urllib.parse import urlparse

    # Validar que la URL no apunte a IPs internas (SSRF protection)
    parsed = urlparse(data.config.get("feed_url", ""))
    if parsed.hostname:
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La URL no puede apuntar a una direccion interna",
                )
        except ValueError:
            pass  # No es una IP, es un dominio - permitir
        # Verificar dominios internos comunes
        internal_domains = ("localhost", "127.0.0.1", "0.0.0.0", "metadata", ".internal", ".local")
        if any(parsed.hostname.startswith(d) or parsed.hostname.endswith(d) for d in internal_domains):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La URL no puede apuntar a un dominio interno",
            )

    source = Source(
        name=data.name,
        source_type=data.source_type,
        config=data.config,
        country=data.country,
        language=data.language,
        fetch_interval=data.fetch_interval,
        priority=data.priority,
        auto_publish=data.auto_publish,
        requires_approval=data.requires_approval,
        target_channels=data.target_channels,
        created_by=_current_user.id,
    )
    session.add(source)
    await session.flush()
    await session.refresh(source)
    return source


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    data: SourceUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
):
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuente no encontrada")

    # SSRF validation on update
    update_data = data.model_dump(exclude_unset=True)
    feed_url = update_data.get("config", {}).get("feed_url", "") if isinstance(update_data.get("config"), dict) else ""
    if feed_url:
        import ipaddress
        from urllib.parse import urlparse
        parsed = urlparse(feed_url)
        if parsed.hostname:
            try:
                ip = ipaddress.ip_address(parsed.hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La URL no puede apuntar a una direccion interna")
            except ValueError:
                pass
            internal_domains = ("localhost", "127.0.0.1", "0.0.0.0", "metadata", ".internal", ".local")
            if any(parsed.hostname.startswith(d) or parsed.hostname.endswith(d) for d in internal_domains):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La URL no puede apuntar a un dominio interno")

    for field, value in update_data.items():
        setattr(source, field, value)

    await session.flush()
    await session.refresh(source)
    return source


@router.post("/{source_id}/pause", response_model=SourceResponse)
async def pause_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
):
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuente no encontrada")
    source.is_paused = True
    source.is_active = False
    await session.flush()
    await session.refresh(source)
    return source


@router.post("/{source_id}/activate", response_model=SourceResponse)
async def activate_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
):
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuente no encontrada")
    source.is_paused = False
    source.is_active = True
    await session.flush()
    await session.refresh(source)
    return source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_admin_user),
):
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuente no encontrada")
    await session.delete(source)
