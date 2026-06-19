"""Workers principal - Scheduler de scraping con APScheduler.
Usa el engine y async_session_factory del backend.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.core.database import async_session_factory
from backend.app.models.news import News
from backend.app.models.telegram_channel import TelegramChannel

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("workers")

MAX_CONCURRENT_SCRAPES = 5
semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)

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

            for entry in feed.entries[:20]:
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
                    img_match = re.search(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", summary_html)
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
    """Pipeline completo para una fuente con dedup por batch."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT name, config->>'feed_url' as url FROM sources WHERE id = :id AND is_active = true AND is_paused = false"),
            {"id": source_id}
        )
        row = result.fetchone()
        if not row:
            return

        name, feed_url = row
        logger.info("Procesando: %s (%s)", name, feed_url)

        items = await scrape_rss_source(source_id, feed_url)
        if not items:
            logger.info("  Sin items para %s", name)
            return

        logger.info("  Items obtenidos: %d", len(items))

        # Batch dedup: unica query para todos los URLs y external_ids
        urls = [it["url"] for it in items if it["url"]]
        ext_ids = [it["external_id"] for it in items if it["external_id"]]

        existing = set()
        if urls:
            rows = await session.execute(
                text("SELECT url FROM news WHERE url = ANY(:urls) AND source_id = :sid"),
                {"urls": urls, "sid": source_id}
            )
            existing.update(row[0] for row in rows if row[0])
        if ext_ids:
            rows = await session.execute(
                text("SELECT external_id FROM news WHERE external_id = ANY(:eids) AND source_id = :sid"),
                {"eids": ext_ids, "sid": source_id}
            )
            existing.update(row[0] for row in rows if row[0])

        new_items = [it for it in items if it["url"] not in existing and it["external_id"] not in existing]

        if not new_items:
            logger.info("  Sin noticias nuevas para %s", name)
            await session.execute(
                text("UPDATE sources SET last_fetched_at = NOW(), error_count = 0 WHERE id = :id"),
                {"id": source_id}
            )
            await session.commit()
            return

        # Insert masivo
        for item in new_items:
            await session.execute(
                text("""
                    INSERT INTO news (source_id, external_id, url, original_title, original_summary,
                                      author, published_at, images, language, status)
                    VALUES (:sid, :eid, :url, :title, :summary,
                            :author, :published, CAST(:images AS jsonb), :lang, 'pending_approval')
                """),
                {
                    "sid": source_id, "eid": item["external_id"], "url": item["url"],
                    "title": item["original_title"], "summary": item["original_summary"],
                    "author": item["author"], "published": item["published_at"],
                    "images": item["images"], "lang": item["language"],
                }
            )

        await session.execute(
            text("UPDATE sources SET last_fetched_at = NOW(), error_count = 0 WHERE id = :id"),
            {"id": source_id}
        )
        await session.commit()
        logger.info("  NOTICIAS NUEVAS: %d para %s", len(new_items), name)


async def scrape_all_sources():
    """Scrapea todas las fuentes activas con concurrencia controlada."""
    async with async_session_factory() as session:
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

    logger.info("Scrapeando %d fuentes (max %d concurrentes)...", len(sources), MAX_CONCURRENT_SCRAPES)

    async def _scrape_one(src_id, name, url):
        async with semaphore:
            try:
                await process_source(src_id)
            except Exception as exc:
                logger.error("Error en %s: %s", name, exc)
                async with async_session_factory() as session:
                    await session.execute(
                        text("UPDATE sources SET error_count = error_count + 1 WHERE id = :id"),
                        {"id": src_id}
                    )
                    await session.commit()

    tasks = [_scrape_one(sid, nm, u) for sid, nm, u in sources]
    await asyncio.gather(*tasks)
    logger.info("Scraping completado")


async def publish_pending():
    """Publica noticias aprobadas pendientes via API directa."""
    token = settings.telegram_bot_token
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado")
        return

    async with async_session_factory() as session:
        from sqlalchemy import select as sql_select

        # Obtener canales activos
        channels_result = await session.execute(
            sql_select(TelegramChannel).where(TelegramChannel.is_active == True)
        )
        channels = channels_result.scalars().all()
        if not channels:
            logger.info("No hay canales activos")
            return

        # Obtener noticias aprobadas
        result = await session.execute(
            text("""
                SELECT id, title, original_title, summary, original_summary,
                       url, author, images, source_id
                FROM news
                WHERE status = 'approved'
                ORDER BY fetched_at ASC
                LIMIT 5
            """)
        )
        news_list = result.fetchall()

        if not news_list:
            return

        logger.info("Publicando %d noticias en %d canales...", len(news_list), len(channels))

        import httpx
        from datetime import datetime, timezone

        for row in news_list:
            news_id, title, orig_title, summary, orig_summary, url, author, images_json, source_id = row
            final_title = title or orig_title or "Sin titulo"
            final_summary = summary or orig_summary or ""

            # Construir mensaje HTML
            import html as html_mod
            safe_title = html_mod.escape(final_title)
            safe_summary = html_mod.escape(final_summary) if final_summary else ""

            lines = [f"\U0001F4F0 <b>{safe_title}</b>"]
            if safe_summary:
                lines.append("")
                lines.append(safe_summary)
            if author:
                lines.append("")
                lines.append(f"\u270F {html_mod.escape(author)}")
            if url:
                escaped_url = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                lines.append("")
                lines.append('\U0001F517 <a href="' + escaped_url + '">Leer mas</a>')

            text = '\n'.join(lines)

            # Obtener primera imagen
            first_image = None
            if images_json and isinstance(images_json, list):
                for img in images_json:
                    if isinstance(img, dict) and img.get("url"):
                        first_image = img["url"]
                        break

            for ch in channels:
                try:
                    if first_image:
                        photo_resp = httpx.post(
                            f"https://api.telegram.org/bot{token}/sendPhoto",
                            json={
                                "chat_id": ch.chat_id,
                                "photo": first_image,
                                "caption": text,
                                "parse_mode": "HTML",
                            },
                            timeout=30,
                        )
                        photo_data = photo_resp.json()
                        if photo_data.get("ok"):
                            resp = photo_resp
                        else:
                            logger.warning(
                                "Foto fallo para news %s (%s), enviando solo texto",
                                news_id, photo_data.get("description", "error"),
                            )
                            resp = httpx.post(
                                f"https://api.telegram.org/bot{token}/sendMessage",
                                json={
                                    "chat_id": ch.chat_id,
                                    "text": text,
                                    "parse_mode": "HTML",
                                    "disable_web_page_preview": True,
                                },
                                timeout=15,
                            )
                    else:
                        resp = httpx.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json={
                                "chat_id": ch.chat_id,
                                "text": text,
                                "parse_mode": "HTML",
                                "disable_web_page_preview": True,
                            },
                            timeout=15,
                        )
                    data = resp.json()
                    if data.get("ok"):
                        logger.info("Publicado news %s en canal %s", news_id, ch.channel_name or ch.chat_id)
                    else:
                        logger.warning("Error publicando news %s: %s", news_id, data.get("description"))
                except Exception as e:
                    logger.error("Error publicando news %s: %s", news_id, e)

            # Marcar como publicada
            await session.execute(
                text("UPDATE news SET status = 'published', published_at = NOW() WHERE id = :id"),
                {"id": news_id}
            )

        await session.commit()


async def main():
    logger.info("=" * 50)
    logger.info("Iniciando Noticiando.pe Workers")
    logger.info("=" * 50)

    scheduler = AsyncIOScheduler()

    scheduler.add_job(scrape_all_sources, "interval", minutes=5, id="scrape_sources")
    scheduler.add_job(publish_pending, "interval", minutes=2, id="publish_news")

    scheduler.start()
    logger.info("Jobs: scrape_sources(5min), publish_news(2min)")

    await scrape_all_sources()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Deteniendo workers...")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
