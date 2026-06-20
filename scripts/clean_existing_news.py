"""One-time migration: limpia el texto de todas las noticias existentes en BD.

Elimina firmas de autor (✏ Nombre), fechas (Actualizado el...),
enlaces "Leer mas", bloques de Instagram, etc. del texto de noticias
que fueron scrapeadas antes de que existiera el pipeline de limpieza.

Uso: python scripts/clean_existing_news.py
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.app.config import settings
from backend.app.core.database import async_session_factory
from backend.app.core.filters import clean_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("clean_news")


async def clean_news_batch(limit: int = 100) -> int:
    """Limpia un lote de noticias y retorna cuantas se actualizaron."""
    updated = 0
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT id, original_summary, original_title
                FROM news
                WHERE original_summary IS NOT NULL
                  AND original_summary != ''
                ORDER BY updated_at DESC
                LIMIT :lim
            """),
            {"lim": limit},
        )
        rows = result.fetchall()

        if not rows:
            return 0

        for news_id, summary, title in rows:
            changes = {}

            if summary:
                cleaned = clean_text(summary)
                if cleaned != summary:
                    changes["original_summary"] = cleaned

            if changes:
                set_clause = ", ".join(
                    f"{col} = :{col}" for col in changes
                )
                params = {"id": news_id, **changes}
                await session.execute(
                    text(f"UPDATE news SET {set_clause} WHERE id = :id"),
                    params,
                )
                updated += 1
                logger.info("  Limpiada news %s", news_id)

        if updated:
            await session.commit()
            logger.info("Lote: %d noticias actualizadas", updated)
        else:
            logger.info("Lote: sin cambios necesarios")

    return updated


async def main():
    logger.info("Iniciando limpieza de noticias existentes...")
    total = 0
    batch = await clean_news_batch(limit=500)
    while batch > 0:
        total += batch
        logger.info("Progreso: %d noticias limpiadas", total)
        batch = await clean_news_batch(limit=500)
    logger.info("Limpieza completada: %d noticias actualizadas", total)


if __name__ == "__main__":
    asyncio.run(main())
