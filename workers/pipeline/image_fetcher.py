"""Fetch de imagenes faltantes para noticias que no tienen imagen en el RSS."""
from __future__ import annotations

import json
import logging
from urllib.parse import urljoin

import httpx
from sqlalchemy import text as sql_text

from backend.app.core.database import async_session_factory

logger = logging.getLogger(__name__)


async def fetch_missing_images(limit: int = 10) -> int:
    """Busca noticias sin imagen y scrapea su URL para extraerlas."""
    fetched = 0
    async with async_session_factory() as session:
        result = await session.execute(
            sql_text("""
                SELECT id, url FROM news
                WHERE (images IS NULL OR images = '[]'::jsonb)
                  AND url IS NOT NULL
                  AND created_at > NOW() - INTERVAL '24 hours'
                LIMIT :lim
            """),
            {"lim": limit},
        )
        news_list = result.fetchall()

        if not news_list:
            return 0

        headers = {
            "User-Agent": "Mozilla/5.0 (NoticiandoBot/1.0; +https://noticiando.pe)"
        }

        for news_id, url in news_list:
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code != 200:
                        continue

                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")
                    images = []

                    for img in soup.find_all("img", src=True)[:3]:
                        src = img["src"]
                        if not src.startswith("http"):
                            src = urljoin(url, src)
                        # Saltar iconos, avatares, etc.
                        if any(k in src.lower() for k in ("icon", "avatar", "logo", "pixel", "1x1")):
                            continue
                        images.append({"url": src, "type": "image/jpeg", "medium": "image"})

                    if images:
                        await session.execute(
                            sql_text("UPDATE news SET images = :images WHERE id = :id"),
                            {"images": json.dumps(images), "id": news_id},
                        )
                        fetched += 1
                        logger.info("Imagenes encontradas para %s: %d", url, len(images))
                    else:
                        logger.debug("Sin imagenes en %s", url)

            except Exception as e:
                logger.debug("Error fetching images for %s: %s", url, e)

        if fetched:
            await session.commit()

    return fetched
