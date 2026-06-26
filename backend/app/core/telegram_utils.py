"""Utilidades compartidas para publicacion en Telegram."""
from __future__ import annotations

import html as html_mod

from backend.app.core.filters import clean_text


MAX_PHOTO_CAPTION = 1024
MAX_TEXT_MESSAGE = 4000  # Below Telegram's 4096 limit
SUMMARY_SAFE_MAX = 600  # Enough room for title + url overhead


def build_telegram_message(
    title: str,
    summary: str = "",
    url: str = "",
    author: str = "",
) -> str:
    """Construye un mensaje HTML seguro para Telegram.

    Aplica limpieza de texto al summary y trunca para asegurar
    que el mensaje quepa dentro de los limites de Telegram
    (1024 chars para caption de foto, 4096 para mensaje de texto).

    Args:
        title: Titulo de la noticia.
        summary: Resumen/contenido (se limpia y trunca).
        url: URL de la noticia original.
        author: Autor o fuente de la noticia.
    """
    safe_title = html_mod.escape(title)

    # Limpiar el summary antes de usarlo
    clean_summary = clean_text(summary) if summary else ""
    safe_summary = html_mod.escape(clean_summary) if clean_summary else ""

    # Truncar summary para que quepa en los limites de Telegram
    if safe_summary and len(safe_summary) > SUMMARY_SAFE_MAX:
        safe_summary = safe_summary[:SUMMARY_SAFE_MAX].rsplit(" ", 1)[0] + "…"

    parts = [f"\U0001F4F0 <b>{safe_title}</b>"]
    if safe_summary:
        parts.append("")
        parts.append(safe_summary)
    if author:
        safe_author = html_mod.escape(author)
        parts.append("")
        parts.append(f"\u270F {safe_author}")
    if url:
        escaped_url = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append("")
        parts.append(f'\U0001F517 <a href="{escaped_url}">Leer mas</a>')

    message = "\n".join(parts)

    # Garantizar que no exceda el limite de texto
    if len(message) > MAX_TEXT_MESSAGE:
        message = message[: MAX_TEXT_MESSAGE - 100].rsplit("\n", 1)[0] + "\n…"

    return message
