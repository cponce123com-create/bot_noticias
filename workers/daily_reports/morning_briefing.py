"""Reporte matutino diario con deduplicacion (solo una vez por dia)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text as sql_text

from backend.app.config import settings
from backend.app.core.database import async_session_factory

logger = logging.getLogger(__name__)


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


async def generate_briefing() -> None:
    """Genera y envia el reporte matutino (solo una vez por dia a las 7 AM)."""
    peru_tz = ZoneInfo("America/Lima")
    now = datetime.now(peru_tz)
    today = now.date()

    # Verificar si ya se envio hoy
    async with async_session_factory() as session:
        result = await session.execute(
            sql_text("SELECT value FROM system_config WHERE key = 'last_briefing_date'")
        )
        row = result.fetchone()
        if row and row[0] == today.isoformat():
            logger.info("Briefing ya enviado hoy, saltando")
            return

    # Solo enviar entre 7:00 y 7:05 AM
    if now.hour != 7 or now.minute > 5:
        return

    lines = [f"\U0001F305 <b>Buenos Dias - {now.strftime('%d/%m/%Y')}</b>"]

    # Tipo de cambio
    if settings.exchange_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://v6.exchangerate-api.com/v6/{settings.exchange_api_key}/latest/USD"
                )
                data = resp.json()
                usd_pen = data.get("conversion_rates", {}).get("PEN", 0)
                eur_pen = data.get("conversion_rates", {}).get("PEN", 0) / (
                    data.get("conversion_rates", {}).get("EUR", 1) or 1
                )
                lines.append("")
                lines.append("\U0001F4B1 <b>Tipo de Cambio:</b>")
                lines.append(f"\U0001F1FA\U0001F1F8 USD/PEN: S/ {usd_pen:.3f}")
                lines.append(f"\U0001F1EA\U0001F1FA EUR/PEN: S/ {eur_pen:.3f}")
        except Exception as e:
            logger.warning("Error obteniendo exchange rates: %s", e)

    # Clima
    if settings.weather_api_key:
        cities = [
            ("Lima", -12.0464, -77.0428),
            ("Arequipa", -16.4090, -71.5375),
            ("Cusco", -13.5319, -71.9675),
            ("Trujillo", -8.1094, -79.0211),
        ]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                lines.append("")
                lines.append("\U0001F326 <b>Clima en Peru:</b>")
                for city, lat, lon in cities:
                    resp = await client.get(
                        "https://api.openweathermap.org/data/2.5/weather",
                        params={
                            "lat": lat, "lon": lon,
                            "appid": settings.weather_api_key,
                            "units": "metric", "lang": "es",
                        },
                    )
                    w = resp.json()
                    temp = w["main"]["temp"]
                    desc = w["weather"][0]["description"]
                    lines.append(f"\U0001F3E0 {city}: {temp:.0f}\u00B0C - {desc}")
        except Exception as e:
            logger.warning("Error obteniendo clima: %s", e)

    # Top noticias
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                sql_text("""
                    SELECT title, url FROM news
                    WHERE status = 'published' AND published_at >= CURRENT_DATE
                    ORDER BY published_at DESC LIMIT 3
                """)
            )
            headlines = result.fetchall()
            if headlines:
                lines.append("")
                lines.append("\U0001F4F0 <b>Noticias del dia:</b>")
                import html as html_mod
                for title, url in headlines:
                    safe_title = html_mod.escape(title or "")
                    lines.append(f"\U0001F539 {safe_title}")
    except Exception as e:
        logger.warning("Error obteniendo noticias: %s", e)

    lines.append("")
    lines.append("\U0001F680 iQue tengas un excelente dia!")

    text = "\n".join(lines)

    # Enviar y marcar como enviado
    async with async_session_factory() as session:
        channels = await session.execute(
            sql_text("SELECT chat_id FROM telegram_channels WHERE is_active = TRUE")
        )
        for row in channels:
            await _publish_text(row[0], text)

        await session.execute(
            sql_text("""
                INSERT INTO system_config (key, value, updated_at)
                VALUES ('last_briefing_date', :date, NOW())
                ON CONFLICT (key) DO UPDATE SET value = :date, updated_at = NOW()
            """),
            {"date": today.isoformat()},
        )
        await session.commit()
        logger.info("Briefing del %s enviado y registrado", today)
