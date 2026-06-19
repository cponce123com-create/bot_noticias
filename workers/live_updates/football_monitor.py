"""Monitoreo de partidos de futbol en vivo - solo notifica goles NUEVOS."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import text as sql_text

from backend.app.config import settings
from backend.app.core.database import async_session_factory

logger = logging.getLogger(__name__)

# Cache simple en memoria
_live_cache: dict = {}
_LIVE_CACHE_TTL = 25  # segundos


async def _publish_text(chat_id: int, text: str) -> None:
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
    """Verifica partidos y notifica SOLO goles nuevos."""
    global _live_cache

    if not settings.football_api_key:
        return

    # Cache de 25 segundos para la API
    import time
    now_ts = time.time()
    cached = _live_cache.get("matches")
    if cached and (now_ts - _live_cache.get("ts", 0)) < _LIVE_CACHE_TTL:
        matches = cached
    else:
        try:
            headers = {
                "X-RapidAPI-Key": settings.football_api_key,
                "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api-football-v1.p.rapidapi.com/v3/fixtures",
                    params={"live": "all"},
                    headers=headers,
                )
                data = resp.json()
            matches = data.get("response", [])
            _live_cache["matches"] = matches
            _live_cache["ts"] = now_ts
        except Exception as e:
            logger.error("Error en API football: %s", e)
            return

    if not matches:
        return

    async with async_session_factory() as session:
        # Obtener ultimo estado conocido de la BD
        result = await session.execute(
            sql_text("""
                SELECT fixture_id, home_score, away_score 
                FROM football_matches 
                WHERE updated_at > NOW() - INTERVAL '2 hours'
            """)
        )
        last_state = {row[0]: (row[1], row[2]) for row in result}

        # Canales activos para notificar
        channels = await session.execute(
            sql_text("SELECT chat_id FROM telegram_channels WHERE is_active = TRUE")
        )
        chat_ids = [row[0] for row in channels]

        if not chat_ids:
            return

        for match in matches:
            fixture_id = match["fixture"]["id"]
            status = match.get("fixture", {}).get("status", {}).get("short", "")
            if status not in ("LIVE", "1H", "2H", "HT", "ET", "P"):
                continue

            home_team = match["teams"]["home"]["name"]
            away_team = match["teams"]["away"]["name"]
            goals_home = match["goals"]["home"] or 0
            goals_away = match["goals"]["away"] or 0
            minute = match.get("fixture", {}).get("status", {}).get("elapsed", "")
            league = match.get("league", {}).get("name", "")

            # Detectar si hay GOL NUEVO
            last_home, last_away = last_state.get(fixture_id, (-1, -1))

            if goals_home > last_home or goals_away > last_away:
                # Determinar goleador (eventos disponibles en otra llamada)
                scorer_info = ""
                if goals_home > last_home:
                    scorer_info = f"\U000026BD {home_team} \U0001F4AA"
                elif goals_away > last_away:
                    scorer_info = f"\U000026BD {away_team} \U0001F4AA"

                marcador_text = (
                    f"\U0001F3BE <b>{home_team} {goals_home} - {goals_away} {away_team}</b>\n"
                    f"\U0001F552 Min {minute}\n"
                    f"{scorer_info}\n"
                    f"\U0001F30D {league}\n"
                    f"#Mundial2026 #EnVivo"
                )

                for chat_id in chat_ids:
                    await _publish_text(chat_id, marcador_text)

                # Actualizar/insertar estado en BD
                await session.execute(
                    sql_text("""
                        INSERT INTO football_matches (fixture_id, home_team, away_team, home_score, away_score, status, minute, league, match_date, updated_at)
                        VALUES (:fid, :home_t, :away_t, :home_s, :away_s, :status, :min, :league, NOW(), NOW())
                        ON CONFLICT (fixture_id) DO UPDATE SET
                            home_score = :home_s, away_score = :away_s, status = :status,
                            minute = :min, updated_at = NOW()
                    """),
                    {
                        "fid": fixture_id,
                        "home_t": home_team,
                        "away_t": away_team,
                        "home_s": goals_home,
                        "away_s": goals_away,
                        "status": status,
                        "min": minute,
                        "league": league,
                    },
                )

            # Si el partido termino, limpiar cache local
            if status in ("FT", "AET", "PEN"):
                _live_cache.pop("matches", None)

        await session.commit()
