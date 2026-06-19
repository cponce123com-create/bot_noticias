"""Scraper de canales Telegram usando Telethon.

Extrae el texto + media (video/imagen) de los posts recientes
de un canal publico, similar a como scrapeamos RSS.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from backend.app.config import settings

logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SESSION_FILE = SESSION_DIR / "telegram_scraper"


async def scrape_telegram_channel(
    source_id: Any,
    channel_username: str,
    max_items: int = 10,
) -> list[dict]:
    """Scrapea los posts mas recientes de un canal de Telegram.

    Args:
        source_id: ID de la fuente en BD
        channel_username: @username del canal (ej: 'CasosOscuros')
        max_items: Maximo de posts a devolver

    Returns:
        Lista de dicts con 'external_id', 'url', 'original_title',
        'original_summary', 'images', 'published_at', 'language'
    """
    api_id = settings.telegram_api_id
    api_hash = settings.telegram_api_hash
    if not api_id or not api_hash:
        logger.warning("TELEGRAM_API_ID o TELEGRAM_API_HASH no configurados")
        return []

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_FILE), api_id, api_hash)

    items = []
    try:
        await client.start()
        if not await client.is_user_authorized():
            logger.error("Telethon no autenticado. Ejecuta 'scripts/auth_telegram.py' primero")
            return []

        entity = await client.get_entity(channel_username)
        async for msg in client.iter_messages(entity, limit=max_items):
            if not msg.text and not msg.media:
                continue

            title = _extract_title(msg.text or "")
            text = (msg.text or "")[:2000]
            post_url = f"https://t.me/{channel_username}/{msg.id}"

            # Extraer media (video o imagen)
            media_url = ""
            if msg.video:
                media_url = f"tg://video/{channel_username}/{msg.id}"
            elif msg.photo:
                media_url = f"tg://photo/{channel_username}/{msg.id}"

            items.append({
                "external_id": post_url,
                "url": post_url,
                "original_title": title[:300],
                "original_summary": text,
                "author": channel_username,
                "published_at": msg.date.replace(tzinfo=timezone.utc) if msg.date else datetime.now(timezone.utc),
                "images": [{"url": media_url, "type": "image/jpeg", "medium": "image"}] if media_url else [],
                "language": "es",
            })

            # Limitar a max_items
            if len(items) >= max_items:
                break

    except Exception as e:
        logger.error("Error scrapeando canal %s: %s", channel_username, e)
    finally:
        await client.disconnect()

    logger.info("  Telegram channel %s: %d items", channel_username, len(items))
    return items


def _extract_title(text: str) -> str:
    """Extrae el titulo del post (primera linea o primeras palabras)."""
    lines = text.strip().split("\n")
    if lines and len(lines[0]) > 10:
        return lines[0][:200]
    return text[:200]
