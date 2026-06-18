"""Workers principal - Scheduler de scraping con APScheduler.

Uso: nix-shell -p stdenv.cc.cc.lib zlib --run '.venv/bin/python workers/main.py'
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.app.config import settings

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("workers")

# Database engine (pooler URL para async)
ASYNC_DSN = settings.database_url.replace("+asyncpg", "").replace("?sslmode=require", "?sslmode=require")
engine = create_async_engine(settings.database_url, echo=False)


async def scrape_rss_source(source_id: uuid.UUID, feed_url: str) -> List[Dict[str, Any]]:
    """Scrapea un feed RSS y retorna items normalizados."""
    items = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(feed_url, headers={
                "User-Agent": "Mozilla/5.0 (NoticiandoBot/1.0; +https://noticiando.pe)"
            })
            resp.raise_for_status()
            import feedparser
            feed = feedparser.parse(resp.content)

            for entry in feed.entries[:20]:  # max 20 por ciclo
                title = (entry.get("title") or "").strip()
                if not title:
                    continue

                link = entry.get("link", "")
                summary = ""
                for tag in ("summary", "description", "subtitle"):
                    val = entry.get(tag, "")
                    if val:
                        summary = val[:300] if isinstance(val, str) else str(val)[:300]
                        break

                published = None
                for attr in ("published_parsed", "updated_parsed"):
                    parsed = getattr(entry, attr, None)
                    if parsed:
                        try:
                            published = datetime(*parsed[:6], tzinfo=timezone.utc)
                        except Exception:
                            pass
                        break

                author = entry.get("author", "") or ""

                images = []
                media_content = entry.get("media_content", []) or []
                for mc in media_content[:3]:
                    if isinstance(mc, dict) and mc.get("url"):
                        images.append({"url": mc["url"], "type": mc.get("type", ""), "medium": "image"})

                if not images:
                    import re
                    summary_html = entry.get("summary", "") or ""
                    img_match = re.search(r'<img[^>]+src=["'](https?://[^"']+)["']', summary_html)
                    if img_match:
                        images.append({"url": img_match.group(1), "type": "image/jpeg", "medium": "image"})

                entry_id = entry.get("id") or entry.get("guid") or link

                items.append({
                    "external_id": entry_id,
                    "url": link,
                    "original_title": title,
                    "original_summary": summary[:300],
                    "author": author,
                    "published_at": published,
                    "images": images,
                    "language": feed.feed.get("language", "es")[:2],
                })
        except Exception as exc:
            logger.error("Error scraping %s: %s", feed_url, exc)
    return items


async def process_source(source_id: uuid.UUID):
    """Pipeline completo para una fuente."""
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT name, config->>'feed_url' as url FROM sources WHERE id = :id AND is_active = true AND is_paused = false"),
            {"id": source_id}
        )
        row = result.fetchone()
        if not row:
            logger.info("Source %s no activa o no encontrada", source_id)
            return

        name, feed_url = row
        logger.info("Procesando: %s (%s)", name, feed_url)

        items = await scrape_rss_source(source_id, feed_url)
        logger.info("  Items encontrados: %d", len(items))

        new_count = 0
        for item in items:
            # Check duplicado por URL
            if item["url"]:
                dup = await session.execute(
                    text("SELECT id FROM news WHERE url = :url AND source_id = :sid LIMIT 1"),
                    {"url": item["url"], "sid": source_id}
                )
                if dup.fetchone():
                    continue

            # Check duplicado por external_id
            if item["external_id"]:
                dup = await session.execute(
                    text("SELECT id FROM news WHERE external_id = :eid AND source_id = :sid LIMIT 1"),
                    {"eid": item["external_id"], "sid": source_id}
                )
                if dup.fetchone():
                    continue

            # Insertar noticia
            await session.execute(
                text("""
                    INSERT INTO news (source_id, external_id, url, original_title, original_summary,
                                      author, published_at, images, language, status)
                    VALUES (:sid, :eid, :url, :title, :summary,
                            :author, :published, :images::jsonb, :lang, 'pending_approval')
                """),
                {
                    "sid": source_id, "eid": item["external_id"], "url": item["url"],
                    "title": item["original_title"], "summary": item["original_summary"],
                    "author": item["author"], "published": item["published_at"],
                    "images": item["images"], "lang": item["language"],
                }
            )
            new_count += 1

        # Actualizar last_fetched_at
        await session.execute(
            text("UPDATE sources SET last_fetched_at = NOW(), error_count = 0 WHERE id = :id"),
            {"id": source_id}
        )
        await session.commit()

        if new_count > 0:
            logger.info("  NOTICIAS NUEVAS: %d", new_count)
        else:
            logger.info("  Sin noticias nuevas")


async def scrape_all_sources():
    """Scrapea todas las fuentes activas."""
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("""
                SELECT id, name, config->>'feed_url' as url
                FROM sources
                WHERE source_type = 'rss' AND is_active = true AND is_paused = false
                  AND (cooldown_until IS NULL OR cooldown_until < NOW())
                  AND error_count < max_errors
                ORDER BY priority DESC
                LIMIT 20
            """)
        )
        sources = result.fetchall()

    if not sources:
        logger.info("No hay fuentes para scrapear")
        return

    logger.info("Scrapeando %d fuentes...", len(sources))
    for src_id, name, url in sources:
        try:
            await process_source(src_id)
        except Exception as exc:
            logger.error("Error en %s: %s", name, exc)
            async with AsyncSession(engine) as session:
                await session.execute(
                    text("UPDATE sources SET error_count = error_count + 1 WHERE id = :id"),
                    {"id": src_id}
                )
                await session.commit()


async def publish_pending():
    """Publica noticias aprobadas pendientes."""
    # Por ahora solo log (implementacion completa requiere el publisher)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT count(*) FROM news WHERE status = 'approved'")
        )
        count = result.scalar() or 0
        if count > 0:
            logger.info("Noticias pendientes de publicar: %d", count)


async def main():
    logger.info("=" * 50)
    logger.info("Iniciando Noticiando.pe Workers")
    logger.info("=" * 50)

    scheduler = AsyncIOScheduler()

    # Scrapear fuentes cada 5 minutos
    scheduler.add_job(scrape_all_sources, "interval", minutes=5, id="scrape_sources")

    # Publicar cada 2 minutos
    scheduler.add_job(publish_pending, "interval", minutes=2, id="publish_news")

    scheduler.start()
    logger.info("Scheduler iniciado. Jobs: scrape_sources (5min), publish_news (2min)")

    # Ejecutar primer ciclo inmediatamente
    await scrape_all_sources()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Deteniendo workers...")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
