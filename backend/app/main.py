"""
Noticiando.pe - Bot de agregacion de noticias para Telegram.
FastAPI application entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1 import v1_router
from backend.app.config import settings
from backend.app.core.database import engine, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: startup y shutdown."""
    logger.info("Iniciando Noticiando.pe...")

    # Crear tablas en desarrollo (en prod usar Alembic)
    if "localhost" in settings.database_url or "neon" in settings.database_url:
        try:
            await init_db()
            logger.info("Base de datos inicializada")
        except Exception as e:
            logger.warning("No se pudo inicializar DB: %s", e)

    yield

    await engine.dispose()
    logger.info("Shutdown completo")


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
