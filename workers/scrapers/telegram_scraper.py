"""Scraper de canales Telegram usando Telethon.

Extrae el texto + media (video/imagen) de los posts recientes
de un canal publico, similar a como scrapeamos RSS.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from backend.app.config import settings

logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SESSION_FILE = SESSION_DIR / "telegram_scraper"

# Patron para detectar texto en negrita de Telegram (entre **...**)
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


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
        'original_summary', 'images', 'videos', 'published_at', 'language'
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

            raw_text = msg.text or ""

            title = _extract_title(raw_text)
            text = _clean_telegram_text(raw_text)
            post_url = f"https://t.me/{channel_username}/{msg.id}"

            # Extraer media (video o imagen) como objetos estructurados
            images_list = []
            videos_list = []

            if msg.video:
                # Descargar thumbnail o construir URL de preview
                video_info = {
                    "url": post_url,
                    "type": "video/mp4",
                    "medium": "video",
                    "thumbnail": f"https://t.me/{channel_username}/{msg.id}?thumb",
                }
                videos_list.append(video_info)
            elif msg.photo:
                # Usar URL directa del mensaje para preview
                images_list.append({
                    "url": f"https://t.me/{channel_username}/{msg.id}?single",
                    "type": "image/jpeg",
                    "medium": "image",
                })

            items.append({
                "external_id": post_url,
                "url": post_url,
                "original_title": title[:300],
                "original_summary": text,
                "author": channel_username,
                "published_at": msg.date.replace(tzinfo=timezone.utc) if msg.date else datetime.now(timezone.utc),
                "images": images_list,
                "videos": videos_list,
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
    """Extrae el titulo del post.

    Prioridad:
    1. Texto entre **negritas** (primer match)
    2. Primera linea significativa (> 10 chars)
    3. Primeros 200 caracteres
    """
    if not text:
        return ""

    # Intentar extraer texto entre **...** (negritas en Telegram)
    bold_matches = BOLD_PATTERN.findall(text)
    for match in bold_matches:
        candidate = match.strip()
        if len(candidate) > 15 and len(candidate) < 200:
            return candidate

    # Fallback: primera linea con suficiente texto
    lines = text.strip().split("
")
    for line in lines:
        line = line.strip()
        # Saltar lineas de emojis solos o muy cortas
        if len(line) > 15 and not line.startswith("**"):
            return line[:200]

    # Fallback final: primeros 200 caracteres
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return clean[:200]


def _clean_telegram_text(text: str) -> str:
    """Limpia el texto de un post de Telegram.

    - Remueve marcadores de negrita **...** (deja el texto interno)
    - Remueve enlaces de suscripcion al canal al final
    - Remueve la linea de autor al final (✏ ...)
    - Remueve saltos de linea excesivos
    - Normaliza el texto
    """
    if not text:
        return ""

    # 1. Reemplazar **texto** con solo texto
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)

    # 2. Remover enlaces de suscripcion como [...](url) al final
    text = re.sub(r"\[.*?\]\(https?://t\.me/\w+\)", "", text)

    # 3. Remover lineas de autor al final (✏ Nombre)
    text = re.sub(r"
✏\s*\w+.*$", "", text.strip())

    # 4. Remover lineas que empiezan con "❗️" u otros emojis de CTA
    text = re.sub(r"
[❗❓❕‼️✅]\s*.*", "", text)

    # 5. Remover lineas de "Suscríbete" o llamadas similares
    text = re.sub(r"(?i)
.*suscr[ií]bete.*", "", text)
    text = re.sub(r"(?i)
.*s[ií]guenos.*", "", text)

    # 6. Normalizar saltos de linea (max 1 seguido)
    text = re.sub(r"
{3,}", "

", text)

    # 7. Normalizar espacios
    text = re.sub(r"[ 	]+", " ", text).strip()

    # 8. Limitar longitud
    if len(text) > 2000:
        text = text[:2000]

    return text
