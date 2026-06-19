"""Scraper adaptativo usando Scrapling para sitios sin RSS o bloqueados.

Usa httpx + Scrapling Selector con adaptive parsing.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from scrapling import Selector

logger = logging.getLogger(__name__)

# Headers para evitar bloqueos
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
}

# Selectores comunes para diferentes portales de noticias
ARTICLE_SELECTORS = [
    "article a[href*='/']",
    "h2 a[href]",
    "h3 a[href]",
    ".story-title a",
    ".entry-title a",
    ".card a[href*='/']",
    ".headline a",
    "[class*='title'] a[href]",
]


async def scrape_scrapling(source_id: Any, name: str, page_url: str, max_items: int = 15) -> list[dict]:
    """Scrapea un sitio de noticias usando Scrapling con adaptive parsing.

    Args:
        source_id: ID de la fuente en BD (para logging)
        name: Nombre de la fuente
        page_url: URL de la pagina principal
        max_items: Maximo de articulos a devolver

    Returns:
        Lista de dicts con formato compatible con scrape_rss_source
    """
    import asyncio
    items = await asyncio.to_thread(_fetch_and_parse, page_url, max_items)
    logger.info("  Scrapling: %d items para %s", len(items), name)
    return items


def _fetch_and_parse(page_url: str, max_items: int) -> list[dict]:
    """Sincrono - ejecutado en thread pool. Obtiene y parsea la pagina."""
    try:
        resp = httpx.get(page_url, headers=HEADERS, follow_redirects=True, timeout=20)
        if resp.status_code != 200:
            logger.warning("  Scrapling: HTTP %s para %s", resp.status_code, page_url)
            return []
    except Exception as e:
        logger.warning("  Scrapling: Error fetching %s: %s", page_url, e)
        return []

    sel = Selector(resp.text, url=page_url)

    # Extraer enlaces a articulos
    seen_urls = set()
    articles = []

    for css in ARTICLE_SELECTORS:
        for link in sel.css(css):
            if len(articles) >= max_items:
                break
            href = link.attrib.get("href", "")
            title = (link.get_all_text() or "").strip()
            if not href or not title or len(title) < 15:
                continue
            full_url = link.urljoin(href)
            if full_url in seen_urls:
                continue
            # Filtrar URLs no-articulo (home, autor, tags, etc.)
            if _is_valid_article_url(full_url, page_url):
                seen_urls.add(full_url)
                articles.append({
                    "external_id": full_url,
                    "url": full_url,
                    "original_title": title[:300],
                    "original_summary": "",
                    "author": "",
                    "published_at": datetime.now(timezone.utc),
                    "images": [],
                    "language": "es",
                })
        if len(articles) >= max_items:
            break

    return articles


def _is_valid_article_url(url: str, base_url: str) -> bool:
    """Filtra URLs que no son articulos de noticias."""
    path = url.replace(base_url.rstrip("/"), "").lstrip("/")
    # Excluir secciones no-noticia
    exclude_patterns = [
        r"^autor/", r"^author/", r"^tag/", r"^video/", r"^multimedia/",
        r"^opinion/", r"^blog/", r"^podcast/", r"^newsletter/",
        r"/tag/", r"/autor/", r"/page/", r"/wp-",
        r"\.jpg$", r"\.png$", r"\.pdf$", r"\.css$", r"\.js$",
    ]
    for pat in exclude_patterns:
        if re.search(pat, path, re.I):
            return False
    return True


# ── Enriquecimiento individual de articulos ──────────────────────────────────

# Selectores para extraer cuerpo del articulo (por orden de preferencia)
BODY_SELECTORS = [
    "article[class*='content']",
    "article",
    "[class*='article-body']",
    "[class*='article__content']",
    "[class*='story-body']",
    "[class*='story-content']",
    "[class*='entry-content']",
    "[class*='post-content']",
    "[class*='nota-content']",
    "[class*='noticia-cuerpo']",
    "[class*='noticia-contenido']",
    "[class*='contenido-nota']",
    "[class*='conten']",  # La Republica, Peru21
    "[itemprop='articleBody']",
    "main",
]

# Selectores para autores
AUTHOR_SELECTORS = [
    "[class*='author'] a",
    "[class*='author']",
    "[class*='byline']",
    "[rel='author']",
    "[itemprop='author']",
]


async def scrape_article(article_url: str) -> dict:
    """Obtiene el texto completo + imagen principal de un articulo.

    Args:
        article_url: URL completa del articulo

    Returns:
        Dict con 'full_text', 'image_url', 'author'
    """
    import asyncio
    return await asyncio.to_thread(_fetch_article, article_url)


def _fetch_article(url: str) -> dict:
    """Sincrono - ejecutado en thread pool."""
    result = {"full_text": "", "image_url": "", "author": ""}

    try:
        resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
        if resp.status_code != 200:
            return result
    except Exception:
        return result

    sel = Selector(resp.text, url=url)

    # 1. Extraer cuerpo del articulo
    for css in BODY_SELECTORS:
        body = sel.css(css)
        if body:
            text = body[0].get_all_text() if isinstance(body, list) else body.get_all_text()
            if text:
                # Limpiar espacios multiples y truncar
                clean = re.sub(r'\s+', ' ', text).strip()
                if len(clean) > 100:
                    result["full_text"] = clean[:3000]
                    break

    # 2. Extraer imagen principal (og:image > primer img en articulo)
    og_image = sel.css("meta[property='og:image']")
    if og_image:
        result["image_url"] = og_image[0].attrib.get("content", "")
    if not result["image_url"]:
        for css in BODY_SELECTORS:
            img = sel.css(f"{css} img")
            if img:
                src = img[0].attrib.get("src", "")
                if src and src.startswith("http"):
                    result["image_url"] = src
                    break

    # 3. Extraer autor
    for css in AUTHOR_SELECTORS:
        author_el = sel.css(css)
        if author_el:
            text = author_el[0].get_all_text().strip() if isinstance(author_el, list) else author_el.get_all_text().strip()
            if text and len(text) < 100:
                result["author"] = text[:80]
                break

    return result
