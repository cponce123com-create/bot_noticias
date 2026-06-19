"""Workers principal - Scheduler de scraping con APScheduler.
Usa el engine y async_session_factory del backend.
"""
from __future__ import annotations

import asyncio
import json
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
    """Scrapea un feed RSS usando el scraper modular RssScraper (con rate limiting, UA rotation, backoff)."""
    from workers.scrapers.rss_scraper import RssScraper

    scraper = RssScraper(
        source_id=source_id,
        source_config={"feed_url": feed_url},
        max_retries=3,
        base_delay=2.0,
        requests_per_minute=20,
    )
    try:
        result = await scraper.run()
        items = result.get("items", [])
        return [item.to_dict() for item in items[:20]]
    except Exception as e:
        logger.error("RssScraper fallo para %s: %s", feed_url, e, exc_info=True)
        return []


async def scrape_google_news_source(source_id: uuid.UUID, keyword: str) -> list[dict]:
    """Scrapea Google News usando gnews."""
    import asyncio
    import re
    from datetime import datetime, timezone

    try:
        items = await asyncio.to_thread(_fetch_gnews, keyword)
    except Exception as e:
        logger.warning("GNews fallo para '%s': %s", keyword, e)
        return []

    result = []
    for article in items:
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        if not title or not url:
            continue

        description = (article.get("description") or "").strip()
        pub_date = article.get("published date") or ""
        publisher = (article.get("publisher") or {}).get("title", "") if isinstance(article.get("publisher"), dict) else (article.get("publisher") or "")

        # Parsear fecha
        published_at = datetime.now(timezone.utc)
        if pub_date:
            try:
                from email.utils import parsedate_to_datetime
                published_at = parsedate_to_datetime(pub_date)
            except Exception:
                pass

        result.append({
            "external_id": url,
            "url": url,
            "original_title": title[:300],
            "original_summary": description[:2000],
            "author": publisher,
            "published_at": published_at,
            "images": [],
            "language": "es",
        })

    return result


def _fetch_gnews(keyword: str) -> list[dict]:
    """Sincrono - ejecutado en thread pool."""
    from gnews import GNews
    gn = GNews(language="es", country="Peru", max_results=10)
    return gn.get_news(keyword)


def _get_base_url(feed_url: str) -> str | None:
    """Extrae la URL base de un feed URL para scraping directo."""
    import re
    # Detectar patrones comunes de feeds
    m = re.match(r'(https?://[^/]+)', feed_url)
    if m:
        base = m.group(1)
        # Si el feed_url tiene subpath de RSS, usar solo el dominio
        rest = feed_url[len(base):]
        if ('rss' in rest.lower() or 'feed' in rest.lower() or 'arc' in rest.lower()
            or 'outbound' in rest.lower() or 'xml' in rest.lower()):
            return base
        return feed_url
    return None


async def process_source(source_id: uuid.UUID):
    """Pipeline completo para una fuente con dedup por batch."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT name, source_type, config FROM sources WHERE id = :id AND is_active = true AND is_paused = false"),
            {"id": source_id}
        )
        row = result.fetchone()
        if not row:
            return

        name, source_type, config = row
        feed_url = config.get("feed_url", "") if isinstance(config, dict) else ""
        keyword = config.get("keyword", "") if isinstance(config, dict) else ""
        logger.info("Procesando: %s (%s)", name, feed_url or keyword)

        # Leer config: auto_approve
        cfg = await session.execute(
            text("SELECT value FROM system_config WHERE key = 'auto_approve'")
        )
        cfg_row = cfg.fetchone()
        auto_approve = cfg_row and cfg_row[0] in (True, "true", "True", "1")

        if source_type == "google_news":
            items = await scrape_google_news_source(source_id, keyword)
        elif source_type == "telegram_channel":
            from workers.scrapers.telegram_scraper import scrape_telegram_channel
            username = config.get("username", "") if isinstance(config, dict) else ""
            if username:
                items = await scrape_telegram_channel(source_id, username, max_items=10)
            else:
                items = []
        else:
            items = await scrape_rss_source(source_id, feed_url)

        # Fallback a Scrapling si RSS no trajo items (sitios bloqueados/sin RSS)
        if not items and source_type == "rss":
            logger.info("  RSS dio 0 items para %s, intentando Scrapling...", name)
            try:
                from workers.scrapers.scrapling_scraper import scrape_scrapling
                # Usar la URL base del sitio (sin el path del feed)
                base_url = _get_base_url(feed_url)
                if base_url:
                    items = await scrape_scrapling(source_id, name, base_url, max_items=15)
            except Exception as e:
                logger.error("  Scrapling fallo para %s: %s", name, e)

        if not items:
            logger.info("  Sin items para %s", name)
            return

        logger.info("  Items obtenidos: %d", len(items))

        # ── Dedup en lote: una sola query con OR ──
        urls = [it["url"] for it in items if it["url"]]
        ext_ids = [it["external_id"] for it in items if it["external_id"]]

        existing_keys = set()
        if urls or ext_ids:
            rows = await session.execute(
                text("""
                    SELECT url, external_id FROM news
                    WHERE source_id = :sid
                      AND (url = ANY(:urls) OR external_id = ANY(:eids))
                """),
                {"sid": source_id, "urls": urls or [""], "eids": ext_ids or [""]},
            )
            for row in rows:
                if row[0]:
                    existing_keys.add(row[0])
                if row[1]:
                    existing_keys.add(row[1])

        new_items = [
            it for it in items
            if it["url"] not in existing_keys and it["external_id"] not in existing_keys
        ]

        if not new_items:
            logger.info("  Sin noticias nuevas para %s", name)
            await session.execute(
                text("UPDATE sources SET last_fetched_at = NOW(), error_count = 0 WHERE id = :id"),
                {"id": source_id}
            )
            await session.commit()
            return

        # ── Insert en lote (executemany) ──
        status_value = "approved" if auto_approve else "pending_approval"
        params = [
            {
                "sid": source_id, "eid": item["external_id"], "url": item["url"],
                "title": item["original_title"], "summary": item["original_summary"],
                "author": item["author"], "published": item["published_at"],
                "images": json.dumps(item["images"]), "lang": item["language"],
                "status": status_value,
            }
            for item in new_items
        ]
        await session.execute(
            text("""
                INSERT INTO news (source_id, external_id, url, original_title, original_summary,
                                  author, published_at, images, language, status)
                VALUES (:sid, :eid, :url, :title, :summary,
                        :author, :published, CAST(:images AS jsonb), :lang, :status)
            """),
            params,
        )

        await session.execute(
            text("UPDATE sources SET last_fetched_at = NOW(), error_count = 0 WHERE id = :id"),
            {"id": source_id}
        )
        await session.commit()
        logger.info("  NOTICIAS NUEVAS: %d para %s", len(new_items), name)

        # ── Enriquecer con texto completo via Scrapling ──
        if new_items and source_type == "rss":
            logger.info("  Enriqueciendo %d articulos para %s...", min(len(new_items), 5), name)
            for item in new_items[:5]:  # Limitar a 5 por fuente
                try:
                    from workers.scrapers.scrapling_scraper import scrape_article
                    enriched = await scrape_article(item["url"])
                    if enriched["full_text"] or enriched["image_url"] or enriched["author"]:
                        update_parts = []
                        params: dict[str, Any] = {"id": item["external_id"]}
                        if enriched["full_text"]:
                            update_parts.append("original_summary = :full_text")
                            params["full_text"] = enriched["full_text"][:2000]
                        if enriched["image_url"]:
                            update_parts.append("images = :images")
                            params["images"] = json.dumps([{"url": enriched["image_url"], "type": "image/jpeg", "medium": "image"}])
                        if enriched["author"]:
                            update_parts.append("author = :author")
                            params["author"] = enriched["author"]
                        if update_parts:
                            async with async_session_factory() as enrich_session:
                                await enrich_session.execute(
                                    text(f"UPDATE news SET {', '.join(update_parts)} WHERE external_id = :id"),
                                    params,
                                )
                                await enrich_session.commit()
                except Exception:
                    logger.debug("  Enrichment fallo para %s", item["url"][:50])


async def scrape_all_sources():
    """Scrapea todas las fuentes activas con concurrencia controlada."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("""
                SELECT id, name, config::text as config_json
                FROM sources
                WHERE source_type IN ('rss', 'google_news', 'telegram_channel') AND is_active = true AND is_paused = false
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

    async def _scrape_one(src_id, name, cfg):
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

    tasks = [_scrape_one(sid, nm, "gnews" if "keyword" in json.loads(cfg) else "rss") for sid, nm, cfg in sources]
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
            from backend.app.core.telegram_utils import build_telegram_message
            msg_text = build_telegram_message(final_title, final_summary, url, author)

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
                                "caption": msg_text,
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
                                    "text": msg_text,
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
                                "text": msg_text,
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


def get_scheduler() -> AsyncIOScheduler:
    """Crea un scheduler con SQLAlchemyJobStore para persistencia."""
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from backend.app.core.database import sanitize_asyncpg_url
    from sqlalchemy import create_engine

    sync_url = settings.database_url_sync or settings.database_url.replace(
        "+asyncpg", ""
    )
    jobstore = SQLAlchemyJobStore(engine=create_engine(sync_url))
    return AsyncIOScheduler(jobstores={"default": jobstore})


async def main():
    """Entry point standalone (usado solo para tests). El scheduler corre en backend/app/main.py."""
    logger.info("Workers standalone: ejecutando un ciclo de scraping...")
    await scrape_all_sources()


if __name__ == "__main__":
    asyncio.run(main())
