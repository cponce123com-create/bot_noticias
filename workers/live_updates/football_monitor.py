"""Monitoreo de partidos de futbol en vivo via ESPN API (gratis, sin API key).

Solo notifica goles NUEVOS comparando con el estado en BD.
"""
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

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


async def _publish_text(chat_id: int, text: str) -> None:
    token = settings.telegram_bot_token
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Error Telegram: %s", data.get("description"))
    except Exception as e:
        logger.error("Error enviando a Telegram: %s", e)


async def check_live_matches() -> None:
    """Verifica partidos ESPN y notifica SOLO goles nuevos."""
    global _live_cache

    import time
    now_ts = time.time()
    cached = _live_cache.get("matches")
    if cached and (now_ts - _live_cache.get("ts", 0)) < _LIVE_CACHE_TTL:
        matches = cached
    else:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(ESPN_URL)
                if resp.status_code != 200:
                    logger.warning("ESPN API respondio %s", resp.status_code)
                    return
                data = resp.json()
            matches = data.get("events", [])
            _live_cache["matches"] = matches
            _live_cache["ts"] = now_ts
        except Exception as e:
            logger.error("Error en ESPN API: %s", e)
            return

    if not matches:
        logger.debug("No hay partidos en ESPN")
        return

    async with async_session_factory() as session:
        # Obtener ultimo estado conocido de la BD
        result = await session.execute(
            sql_text("""
                SELECT fixture_id, home_score, away_score 
                FROM football_matches 
                WHERE updated_at > NOW() - INTERVAL '4 hours'
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

        for event in matches:
            status_type = event.get("status", {}).get("type", {})
            status_desc = status_type.get("description", "")
            detail = status_type.get("detail", "")

            # Solo partidos EN VIVO (no scheduled, no full time)
            if "Half" not in status_desc and "Live" not in status_desc and status_desc not in ("In Progress",):
                continue

            match_name = event.get("shortName") or event.get("name", "?")
            comps = event.get("competitions", [])
            if not comps:
                continue
            comp = comps[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            home = competitors[0]
            away = competitors[1]
            home_team = home.get("team", {}).get("displayName", "?")
            away_team = away.get("team", {}).get("displayName", "?")
            home_abbr = home.get("team", {}).get("abbreviation", "?")
            away_abbr = away.get("team", {}).get("abbreviation", "?")

            try:
                goals_home = int(home.get("score", "0"))
                goals_away = int(away.get("score", "0"))
            except (ValueError, TypeError):
                goals_home = 0
                goals_away = 0

            # Usar hash del match_name como fixture_id (entero de 8 posiciones para PK)
            import hashlib
            fixture_id = int(hashlib.sha256(match_name.encode()).hexdigest()[:7], 16)

            # Detectar si hay GOL NUEVO
            last_home, last_away = last_state.get(fixture_id, (-1, -1))

            if goals_home > last_home or goals_away > last_away:
                scorer_info = ""
                if goals_home > last_home:
                    scorer_info = f"\U000026BD {home_abbr} \U0001F4AA"
                elif goals_away > last_away:
                    scorer_info = f"\U000026BD {away_abbr} \U0001F4AA"

                marcador_text = (
                    f"\U0001F3BE <b>{home_abbr} {goals_home} - {goals_away} {away_abbr}</b>\n"
                    f"\U0001F552 {detail}\n"
                    f"{scorer_info}\n"
                    f"\U0001F30D Mundial 2026\n"
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
                        "status": status_desc,
                        "min": detail,
                        "league": "Mundial 2026",
                    },
                )

            # Si el partido termino, limpiar cache local
            if "Full Time" in status_desc or "Final" in status_desc:
                _live_cache.pop("matches", None)

        await session.commit()
