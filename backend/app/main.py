"""Noticiando.pe - Bot de agregacion de noticias para Telegram.
FastAPI application entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.api.v1 import v1_router
from backend.app.config import settings
from backend.app.core.database import engine, init_db

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def ensure_admin_user():
    """Crea el admin por defecto si no existe."""
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from backend.app.core.database import (
            create_asyncpg_ssl_context,
            sanitize_asyncpg_url,
        )

        safe_url = sanitize_asyncpg_url(settings.database_url)
        eng = create_async_engine(
            safe_url,
            echo=False,
            connect_args={"ssl": create_asyncpg_ssl_context()},
        )
        async with AsyncSession(eng) as session:
            result = await session.execute(
                text("SELECT id, password_hash FROM users WHERE email = :email"),
                {"email": settings.admin_email},
            )
            row = result.fetchone()
            from backend.app.core.security import get_password_hash, verify_password

            if not row:
                await session.execute(
                    text("""
                        INSERT INTO users (username, email, password_hash, role, is_active)
                        VALUES (:user, :email, :pw, 'admin', true)
                    """),
                    {
                        "user": settings.admin_email.split("@")[0],
                        "email": settings.admin_email,
                        "pw": get_password_hash(settings.admin_password),
                    },
                )
                await session.commit()
                logger.info("Admin user created: %s", settings.admin_email)
            else:
                # Verificar si la password cambió
                stored_hash = row[1]
                if not verify_password(settings.admin_password, stored_hash):
                    new_hash = get_password_hash(settings.admin_password)
                    await session.execute(
                        text("UPDATE users SET password_hash = :pw WHERE email = :email"),
                        {"pw": new_hash, "email": settings.admin_email},
                    )
                    await session.commit()
                    logger.info("Admin password updated: %s", settings.admin_email)
                else:
                    logger.info("Admin user exists: %s", settings.admin_email)
        await eng.dispose()
    except Exception as e:
        logger.warning("Could not verify admin user: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: startup y shutdown."""
    logger.info("Iniciando Noticiando.pe...")

    if settings.run_migrations:
        try:
            await init_db()
            logger.info("Base de datos inicializada")
        except Exception as e:
            logger.warning("No se pudo inicializar DB: %s", e)

    await ensure_admin_user()

    # ── Iniciar scheduler de background (scraping + publishing) ──
    scheduler = None
    if settings.enable_scheduler:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from workers.main import publish_pending, scrape_all_sources

            scheduler = AsyncIOScheduler()
            scheduler.add_job(scrape_all_sources, "interval", minutes=5, id="scrape_sources")
            scheduler.add_job(publish_pending, "interval", minutes=2, id="publish_news")
            scheduler.start()
            logger.info("Scheduler iniciado: scrape_sources(5min), publish_news(2min)")

            # Primer ciclo inmediato
            import asyncio
            asyncio.ensure_future(scrape_all_sources())

            # ── Jobs opcionales (requieren API keys) ──
            try:
                from workers.live_updates.football_monitor import check_live_matches
                scheduler.add_job(check_live_matches, "interval", seconds=30, id="football_live")
                logger.info("Job football_live agregado (c/30s)")
            except Exception as e:
                logger.debug("No se pudo agregar football_live: %s", e)

            try:
                from workers.daily_reports.morning_briefing import generate_briefing
                scheduler.add_job(generate_briefing, "interval", hours=1, id="morning_briefing")
                logger.info("Job morning_briefing agregado (c/1h)")
            except Exception as e:
                logger.debug("No se pudo agregar morning_briefing: %s", e)

            # ── Facebook token refresh (c/45 días) ──
            if settings.facebook_page_id and settings.facebook_page_token:
                try:
                    from workers.publishers.facebook_publisher import refresh_facebook_token
                    scheduler.add_job(refresh_facebook_token, "interval", days=45, id="facebook_token_refresh")
                    logger.info("Job facebook_token_refresh agregado (c/45d)")
                except Exception as e:
                    logger.debug("No se pudo agregar facebook_token_refresh: %s", e)
        except Exception as e:
            logger.warning("No se pudo iniciar scheduler: %s", e)
    else:
        logger.info("Scheduler deshabilitado via ENABLE_SCHEDULER=false")

    yield

    # ── Shutdown ──
    if scheduler:
        scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("Shutdown completo")


app = FastAPI(
    title="Noticiando.pe API",
    description="API de agregacion de noticias para Telegram - @noticiando_pe_bot",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - leer origenes permitidos desde variable de entorno
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "bot": "@noticiando_pe_bot"}

# API v1 - configure rate limiter
from backend.app.api.v1.auth import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
