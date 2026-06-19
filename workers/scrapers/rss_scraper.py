"""Scraper para fuentes RSS/Atom.

Utiliza feedparser para parsear feeds y extraer articulos en formato
normalizado ScrapedItem. Maneja RSS 2.0, RSS 1.0, Atom y feeds con
extensiones (Dublin Core, Slash, Media RSS).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import feedparser
from dateutil import parser as dateparser

from workers.scrapers.base import AsyncScraper, ScrapedItem

logger = logging.getLogger(__name__)


class RssScraper(AsyncScraper):
    """Scraper que consume fuentes RSS/Atom y retorna items normalizados."""

    # Etiquetas de resumen/descripcion por orden de preferencia
    _SUMMARY_TAGS = ["summary", "description", "subtitle", "abstract", "content"]
    # Etiquetas de cuerpo completo
    _BODY_TAGS = ["content", "content:encoded", "body", "article:body"]

    async def fetch(self) -> bytes:
        """Descarga el feed RSS/Atom via HTTP."""
        url = self.source_config.get("feed_url") or self.source_config.get("url", "")
        if not url:
            raise ValueError("La configuracion de la fuente debe incluir 'feed_url' o 'url'")
        return await self._fetch_with_retries(url)

    async def parse(self, raw: bytes) -> List[ScrapedItem]:
        """Parsea el XML del feed y extrae los articulos."""
        feed = feedparser.parse(raw)

        if feed.bozo and not feed.entries:
            error_msg = str(feed.bozo_exception) if feed.bozo_exception else "XML malformado"
            logger.error("Feed malformado para source %s: %s", self.source_id, error_msg)
            return []

        # Metadata global del feed (canal)
        feed_channel = feed.feed.get("title", "Unknown Feed")
        feed_link = feed.feed.get("link", "")
        feed_language = self._extract_feed_language(feed)

        items: List[ScrapedItem] = []
        seen_guids: set = set()

        for entry in feed.entries:
            try:
                item = self._parse_entry(entry, feed_channel, feed_link, feed_language)
                if item is None:
                    continue

                # Deduplicacion temprana por external_id dentro del mismo batch
                ext_id = item.external_id or hashlib.sha256(
                    (item.url or item.original_title or "").encode()
                ).hexdigest()
                if ext_id in seen_guids:
                    continue
                seen_guids.add(ext_id)
                if item.external_id is None:
                    item.external_id = ext_id

                items.append(item)

            except Exception as exc:
                logger.warning(
                    "[%s] Error parseando entry: %s - %s",
                    self.source_id, exc, getattr(entry, "link", "unknown"),
                )
                continue

        logger.info(
            "[%s] Feed '%s': %d/%d entradas parseadas",
            self.source_id, feed_channel, len(items), len(feed.entries),
        )
        return items

    # ── Metodos auxiliares de parseo ─────────────────────────────────────────

    def _extract_feed_language(self, feed: feedparser.FeedParserDict) -> str:
        """Extrae el idioma del feed."""
        lang = (
            feed.feed.get("language")
            or feed.feed.get("xml:lang")
            or feed.feed.get("dc_language")
            or ""
        )
        if lang and len(lang) >= 2:
            return lang[:2].lower()
        return "es"

    def _parse_entry(
        self,
        entry: feedparser.FeedParserDict,
        feed_channel: str,
        feed_link: str,
        feed_language: str,
    ) -> Optional[ScrapedItem]:
        """Convierte una entrada de feedparser en ScrapedItem."""
        # ── Titulo ───────────────────────────────────────────────────────
        title = (entry.get("title") or "").strip()
        if not title:
            return None

        # ── URL / Link ───────────────────────────────────────────────────
        url = self._extract_link(entry, feed_link)
        if not url:
            logger.debug("Entry sin link valido, saltando: %s", title[:50])
            return None

        # ── External ID (guid / id) ──────────────────────────────────────
        external_id = entry.get("id") or entry.get("guid") or entry.get("link") or ""

        # ── Fecha de publicacion ─────────────────────────────────────────
        published_at = self._parse_entry_date(entry)

        # ── Autor ────────────────────────────────────────────────────────
        author = self._extract_author(entry)

        # ── Resumen y cuerpo ─────────────────────────────────────────────
        summary = self._extract_summary(entry)
        body = self._extract_body(entry)

        # ── Imagenes ─────────────────────────────────────────────────────
        images = self._extract_images(entry, url)

        # ── Videos ───────────────────────────────────────────────────────
        videos = self._extract_videos(entry)

        # ── Hashtags / Tags / Categorias ─────────────────────────────────
        hashtags = self._extract_tags(entry)

        # ── Metadata extra ───────────────────────────────────────────────
        meta: Dict[str, Any] = {
            "feed_title": feed_channel,
            "feed_link": feed_link,
            "source_entry_id": entry.get("id", ""),
        }

        return ScrapedItem(
            external_id=external_id,
            url=url,
            original_title=title,
            original_summary=summary,
            original_body=body,
            author=author,
            published_at=published_at,
            images=images,
            videos=videos,
            language=feed_language,
            hashtags=hashtags,
            metadata=meta,
        )

    @staticmethod
    def _extract_link(entry: feedparser.FeedParserDict, fallback_url: str) -> str:
        """Extrae el primer link valido de la entrada."""
        # Atom: entry.link es un objeto con href
        links = entry.get("links", [])
        for link in links:
            href = link.get("href", "")
            rel = link.get("rel", "alternate")
            if href and rel in ("alternate", "self", ""):
                return href

        # RSS: entry.link es string directo
        direct = entry.get("link")
        if direct and isinstance(direct, str) and direct.startswith("http"):
            return direct

        # Si solo tenemos el link del feed, devolvemos ese
        if fallback_url:
            return fallback_url

        return ""

    def _parse_entry_date(self, entry: feedparser.FeedParserDict) -> Optional[datetime]:
        """Parsea la fecha de publicacion probando multiples campos."""
        # feedparser ya parsea published_parsed / updated_parsed
        for attr in ("published_parsed", "updated_parsed", "created_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                try:
                    return datetime(*parsed[:6], tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    continue

        # Fallback: parseo manual de strings
        for attr in ("published", "updated", "created", "dc:date", "date"):
            raw = entry.get(attr) or ""
            if raw:
                try:
                    dt = dateparser.parse(raw)
                    if dt and dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except (ValueError, TypeError):
                    continue

        return None

    @staticmethod
    def _extract_author(entry: feedparser.FeedParserDict) -> Optional[str]:
        """Extrae el nombre del autor desde varios formatos."""
        # Atom: entry.author
        author = entry.get("author") or ""
        if author and isinstance(author, str):
            return author.strip()

        # Dublin Core: dc:creator
        dc_creator = entry.get("dc_creator") or ""
        if dc_creator and isinstance(dc_creator, str):
            return dc_creator.strip()

        # Media: credit
        media_credit = entry.get("media_credit") or ""
        if media_credit and isinstance(media_credit, str):
            return media_credit.strip()

        # author_detail (Atom)
        author_detail = entry.get("author_detail")
        if author_detail and isinstance(author_detail, dict):
            name = author_detail.get("name", "")
            if name:
                return name.strip()

        return None

    def _extract_summary(self, entry: feedparser.FeedParserDict) -> Optional[str]:
        """Extrae el resumen/descripcion de la entrada."""
        for tag in self._SUMMARY_TAGS:
            value = entry.get(tag)
            if value:
                if isinstance(value, list) and len(value) > 0:
                    value = value[0].get("value", "") if isinstance(value[0], dict) else str(value[0])
                text = str(value).strip()
                if text:
                    return self._clean_html(text)
        return None

    def _extract_body(self, entry: feedparser.FeedParserDict) -> Optional[str]:
        """Extrae el cuerpo completo del articulo."""
        for tag in self._BODY_TAGS:
            value = entry.get(tag)
            if value:
                if isinstance(value, list):
                    # Atom: content es lista de dicts con 'value' y 'type'
                    for item in value:
                        if isinstance(item, dict) and item.get("type") in ("text/html", "html", "text", ""):
                            text = item.get("value", "") or ""
                            if text.strip():
                                return self._clean_html(text)
                else:
                    text = str(value).strip()
                    if text:
                        return self._clean_html(text)
        return None

    def _extract_images(self, entry: feedparser.FeedParserDict, article_url: str) -> List[Dict[str, Any]]:
        """Extrae imagenes del entry (Media RSS, enclosures, Open Graph)."""
        images: List[Dict[str, Any]] = []
        seen_urls: set = set()

        # Media RSS: media:content / media:thumbnail
        media_content = entry.get("media_content", []) or []
        for mc in media_content:
            if isinstance(mc, dict):
                url = mc.get("url", "")
                if url and url not in seen_urls and self._is_image_url(url):
                    seen_urls.add(url)
                    images.append({
                        "url": url,
                        "type": mc.get("type", ""),
                        "width": mc.get("width"),
                        "height": mc.get("height"),
                        "medium": mc.get("medium", "image"),
                    })

        media_thumbnail = entry.get("media_thumbnail", []) or []
        for mt in media_thumbnail:
            if isinstance(mt, dict):
                url = mt.get("url", "")
                if url and url not in seen_urls and self._is_image_url(url):
                    seen_urls.add(url)
                    images.append({
                        "url": url,
                        "type": "image/jpeg",
                        "width": mt.get("width"),
                        "height": mt.get("height"),
                        "medium": "image",
                    })

        # Enclosures (podcast/video/image)
        for enc in entry.get("enclosures", []):
            if isinstance(enc, dict):
                url = enc.get("href", "") or enc.get("url", "")
                mime = enc.get("type", "")
                if url and url not in seen_urls and mime.startswith("image/"):
                    seen_urls.add(url)
                    images.append({
                        "url": url,
                        "type": mime,
                        "width": enc.get("width"),
                        "height": enc.get("height"),
                        "medium": "image",
                    })

        # Fallback: buscar imagen en summary (primer <img>)
        if not images:
            summary = entry.get("summary", "") or ""
            img_url = self._extract_first_image_from_html(summary)
            if img_url and img_url not in seen_urls:
                seen_urls.add(img_url)
                images.append({
                    "url": img_url,
                    "type": "image/jpeg",
                    "medium": "image",
                })

        return images

    @staticmethod
    def _extract_videos(entry: feedparser.FeedParserDict) -> List[Dict[str, Any]]:
        """Extrae videos del entry (enclosures, Media RSS)."""
        videos: List[Dict[str, Any]] = []
        seen_urls: set = set()

        # Media RSS
        media_content = entry.get("media_content", []) or []
        for mc in media_content:
            if isinstance(mc, dict):
                url = mc.get("url", "")
                mime = mc.get("type", "")
                medium = mc.get("medium", "")
                if url and url not in seen_urls and (mime.startswith("video/") or medium == "video"):
                    seen_urls.add(url)
                    videos.append({
                        "url": url,
                        "type": mime,
                        "width": mc.get("width"),
                        "height": mc.get("height"),
                        "medium": "video",
                    })

        # Enclosures de video
        for enc in entry.get("enclosures", []):
            if isinstance(enc, dict):
                url = enc.get("href", "") or enc.get("url", "")
                mime = enc.get("type", "")
                if url and url not in seen_urls and mime.startswith("video/"):
                    seen_urls.add(url)
                    videos.append({
                        "url": url,
                        "type": mime,
                        "width": enc.get("width"),
                        "height": enc.get("height"),
                        "medium": "video",
                    })

        return videos

    @staticmethod
    def _extract_tags(entry: feedparser.FeedParserDict) -> List[str]:
        """Extrae tags/categorias del entry."""
        tags: List[str] = []
        seen: set = set()

        for tag in entry.get("tags", []):
            if isinstance(tag, dict):
                term = tag.get("term", "") or tag.get("label", "") or ""
                if term and term.lower() not in seen:
                    seen.add(term.lower())
                    tags.append(term)

        # Dublin Core subject
        dc_subject = entry.get("dc_subject", [])
        if isinstance(dc_subject, list):
            for subj in dc_subject:
                if isinstance(subj, str) and subj.lower() not in seen:
                    seen.add(subj.lower())
                    tags.append(subj)

        # Limitar a 10 tags
        return tags[:10]

    @staticmethod
    def _is_image_url(url: str) -> bool:
        """Verifica si una URL parece ser de una imagen por extension."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")
        return any(path.endswith(ext) for ext in image_exts)

    @staticmethod
    def _extract_first_image_from_html(html: str) -> Optional[str]:
        """Extrae la URL de la primera imagen en un fragmento HTML."""
        if not html:
            return None
        import re
        match = re.search(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", html, re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _clean_html(text: str) -> str:
        """Elimina etiquetas HTML basico y normaliza espacios."""
        import re
        # Remover etiquetas
        text = re.sub(r"<[^>]+>", " ", text)
        # Normalizar espacios
        text = re.sub(r"\s+", " ", text).strip()
        return text
