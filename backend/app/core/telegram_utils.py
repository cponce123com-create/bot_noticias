"""Utilidades compartidas para publicacion en Telegram."""
from __future__ import annotations

import html as html_mod


def build_telegram_message(
    title: str,
    summary: str = "",
    url: str = "",
    author: str = "",
) -> str:
    """Construye un mensaje HTML seguro para Telegram."""
    safe_title = html_mod.escape(title)
    safe_summary = html_mod.escape(summary) if summary else ""
    safe_author = html_mod.escape(author) if author else ""

    parts = [f"\U0001F4F0 <b>{safe_title}</b>"]
    if safe_summary:
        parts.append("")
        parts.append(safe_summary)
    if safe_author:
        parts.append("")
        parts.append(f"\u270F {safe_author}")
    if url:
        escaped_url = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append("")
        parts.append(f'\U0001F517 <a href="{escaped_url}">Leer mas</a>')

    return "\n".join(parts)
