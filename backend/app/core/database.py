"""
Conexion asincrona a PostgreSQL (Neon) usando SQLAlchemy 2.0.
Limpia la URL de parametros no soportados por asyncpg (como ?sslmode=require)
y configura SSL via connect_args.
"""
from __future__ import annotations

import ssl
from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import settings


def sanitize_asyncpg_url(url: str) -> str:
    """
    Elimina TODOS los parametros de query string (?sslmode=require,
    ?channel_binding=require, etc.) de la URL, ya que asyncpg no los soporta.
    La configuracion SSL se pasa via connect_args a create_async_engine.
    """
    parsed = urlparse(url)
    if parsed.query:
        parsed = parsed._replace(query="")
    return str(urlunparse(parsed))


def create_asyncpg_ssl_context() -> ssl.SSLContext:
    """Crea un SSLContext para conexion segura a Neon via asyncpg."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


# Sanitizar URL eliminando sslmode (no soportado por asyncpg)
_safe_db_url = sanitize_asyncpg_url(settings.database_url)

engine = create_async_engine(
    _safe_db_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=settings.db_pool_pre_ping,
    pool_recycle=300,
    pool_timeout=30,
    connect_args={"ssl": create_asyncpg_ssl_context()},
    echo=False,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
