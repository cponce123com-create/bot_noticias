"""Utilidades compartidas para publicacion en Telegram."""
from __future__ import annotations

import html as html_mod

from backend.app.core.filters import clean_text


def build_telegram_message(
    title: str,
    summary: str = "",
    url: str = "",
    author: str = "",
) -> str:
    """Construye un mensaje HTML seguro para Telegram.

    Aplica limpieza de texto al summary (remueve autorias,
    fechas, 'Leer mas', etc.) antes de construir el mensaje.
    """
    safe_title = html_mod.escape(title)

    # Limpiar el summary antes de usarlo
    clean_summary = clean_text(summary) if summary else ""
    safe_summary = html_mod.escape(clean_summary) if clean_summary else ""

    parts = [f"\U0001F4F0 <b>{safe_title}</b>"]
    if safe_summary:
        parts.append("")
        parts.append(safe_summary)
    if url:
        escaped_url = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append("")
        parts.append(f'\U0001F517 <a href="{escaped_url}">Leer mas</a>')

    return "\n".join(parts)
