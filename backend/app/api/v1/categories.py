from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.core.security import get_current_user
from backend.app.models.category import Category
from backend.app.models.user import User
from backend.app.schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/", response_model=list[CategoryResponse])
async def list_categories(
    is_active: Optional[bool] = Query(None),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    query = select(Category).order_by(Category.name)
    if is_active is not None:
        query = query.where(Category.is_active == is_active)
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    existing = await session.execute(
        select(Category).where(
            (Category.name == data.name) | (Category.slug == data.slug)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Categoria ya existe",
        )

    category = Category(**data.model_dump())
    session.add(category)
    await session.flush()
    await session.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    category = await session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria no encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await session.flush()
    await session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    category = await session.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria no encontrada")
    await session.delete(category)
