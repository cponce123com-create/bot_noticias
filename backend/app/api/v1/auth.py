from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.config import settings
from backend.app.core.security import (
    create_access_token,
    get_admin_user,
    get_current_user,
    get_password_hash,
    verify_password,
)
from backend.app.models.user import User
from backend.app.schemas.user import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, session: AsyncSession = Depends(get_session), _current_user: User = Depends(get_admin_user)):
    existing = await session.execute(
        select(User).where((User.email == data.email) | (User.username == data.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email o usuario ya registrado",
        )

    user = User(
        username=data.username,
        email=data.email,
        password_hash=get_password_hash(data.password),
        role=data.role,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    data: UserLogin,
    response: Response,
    session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado",
        )

    user.last_login = datetime.now(timezone.utc)
    await session.flush()
    token = create_access_token({"sub": str(user.id)})

    # Setear cookie httpOnly en vez de solo devolver token en body
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        path="/api",
        secure=True,
    )

    return TokenResponse(user=UserResponse.model_validate(user))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        path="/api",
        httponly=True,
        samesite="lax",
    )
    return {"status": "ok", "message": "Sesion cerrada"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
