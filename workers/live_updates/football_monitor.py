"""Monitoreo de partidos de futbol en vivo."""
from __future__ import annotations

import asyncio
import logging

import httpx

from backend.app.config import settings
from backend.app.core.database import async_session_factory

logger = logging.getLogger(__name__)


async def _publish_text(chat_id: int, text: str) -> None:
    """Publica mensaje de texto a un canal via API de Telegram."""
    token = settings.telegram_bot_token
    if not token:
        return
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("Error Telegram: %s", data.get("description"))
    except Exception as e:
        logger.error("Error enviando a Telegram: %s", e)


async def check_live_matches() -> None:
    """Verifica partidos en vivo y notifica goles nuevos."""
    if not settings.football_api_key:
        return

    headers = {
        "X-RapidAPI-Key": settings.football_api_key,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api-football-v1.p.rapidapi.com/v3/fixtures",
                params={"live": "all"},
                headers=headers,
            )
            data = resp.json()

        matches = data.get("response", [])
        if not matches:
            return

        async with async_session_factory() as session:
            from sqlalchemy import text as sql_text
            result = await session.execute(
                sql_text("SELECT chat_id FROM telegram_channels WHERE is_active = TRUE")
            )
            chat_ids = [row[0] for row in result]

        if not chat_ids:
            return

        for match in matches:
            fixture_id = match["fixture"]["id"]
            status = match.get("fixture", {}).get("status", {}).get("short", "")
            if status not in ("LIVE", "1H", "2H", "HT", "ET", "P"):
                continue

            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            goals_home = match["goals"]["home"] or 0
            goals_away = match["goals"]["away"] or 0
            minute = match.get("fixture", {}).get("status", {}).get("elapsed", "")

            text = (
                f"\U0001F3BE <b>{home} {goals_home}-{goals_away} {away}</b>\n"
                f"\U0001F552 Minuto {minute}\n"
                f"\U0001F30D Mundial 2026"
            )

            for chat_id in chat_ids:
                await _publish_text(chat_id, text)

    except Exception as e:
        logger.error("Error en football monitor: %s", e)
