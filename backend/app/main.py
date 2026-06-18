\"\"\"
Noticiando.pe - Bot de agregacion de noticias para Telegram.
FastAPI application entry point.
\"\"\"
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1 import v1_router
from backend.app.config import settings
from backend.app.core.database import engine, init_db

logger = logging.getLogger(__name__)


async def ensure_admin_user():
    \"\"\"Crea el admin por defecto si no existe.\"\"\"
    try:
        from sqlalchemy import select, text
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        eng = create_async_engine(settings.database_url, echo=False)
        async with AsyncSession(eng) as session:
            result = await session.execute(
                text(\"SELECT id FROM users WHERE email = :email\"),
                {\"email\": settings.admin_email},
            )
            if not result.fetchone():
                from backend.app.core.security import get_password_hash
                await session.execute(
                    text(\"\"\"
                        INSERT INTO users (username, email, password_hash, role, is_active)
                        VALUES (:user, :email, :pw, 'admin', true)
                    \"\"\"),
                    {
                        \"user\": settings.admin_email.split(\"@\")[0],
                        \"email\": settings.admin_email,
                        \"pw\": get_password_hash(settings.admin_password),
                    },
                )
                await session.commit()
                logger.info(\"Admin user created: %s\", settings.admin_email)
            else:
                logger.info(\"Admin user exists: %s\", settings.admin_email)
        await eng.dispose()
    except Exception as e:
        logger.warning(\"Could not verify admin user: %s\", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    \"\"\"Lifecycle: startup y shutdown.\"\"\"
    logger.info(\"Iniciando Noticiando.pe...\")

    if \"localhost\" in settings.database_url or \"neon\" in settings.database_url:
        try:
            await init_db()
            logger.info(\"Base de datos inicializada\")
        except Exception as e:
            logger.warning(\"No se pudo inicializar DB: %s\", e)

    await ensure_admin_user()

    yield

    await engine.dispose()
    logger.info(\"Shutdown completo\")


app = FastAPI(
    title="Noticiando.pe API",
    description="API de agregacion de noticias para Telegram - @noticiando_pe_bot",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - permitir frontend en Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://noticiando-pe.onrender.com",
        "https://noticiando-pe-web.onrender.com",
        "https://bot-noticias-dx2d.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "bot": "@noticiando_pe_bot"}

# API v1
app.include_router(v1_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
