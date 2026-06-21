"""Publicador de noticias en Facebook Page via Graph API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FacebookPublicationPayload:
    title: str
    summary: Optional[str] = None
    url: Optional[str] = None
    images: List[Dict[str, Any]] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)
    news_id: Optional[str] = None
    published_at: Optional[datetime] = None
    author: Optional[str] = None


class FacebookPublisher:
    """Publica noticias en una Facebook Page via Graph API v19+.

    Soporta:
    - Link posts: POST /{page-id}/feed (message + link)
    - Photo posts: POST /{page-id}/photos (url + caption)
    - Auto-refresh de Page Access Token cada 45 d\u00edas

    Uso:
        pub = FacebookPublisher()
        post_id = await pub.publish(payload)
    """

    GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

    def __init__(self) -> None:
        self.page_id = settings.facebook_page_id
        self.access_token = settings.facebook_page_token
        self.app_id = settings.facebook_app_id
        self.app_secret = settings.facebook_app_secret
        self.max_retries = 3
        self.base_delay = 2.0

    async def publish_link(self, payload: FacebookPublicationPayload) -> Optional[str]:
        """Publica un link (noticia) en el feed de la p\u00e1gina."""
        message = self._build_message(payload, include_url=False)
        data: Dict[str, str] = {
            "message": message,
            "access_token": self.access_token,
        }
        if payload.url:
            data["link"] = payload.url
        return await self._post("feed", data)

    async def publish_photo(self, payload: FacebookPublicationPayload) -> Optional[str]:
        """Publica una foto con caption en el feed."""
        image_url = self._get_best_image(payload)
        if not image_url:
            return await self.publish_link(payload)
        message = self._build_message(payload)
        data = {
            "url": image_url,
            "caption": message,
            "access_token": self.access_token,
        }
        return await self._post("photos", data, timeout=60)

    async def publish(self, payload: FacebookPublicationPayload) -> Optional[str]:
        """M\u00e9todo unificado: publica link post con la mejor imagen disponible."""
        return await self.publish_link(payload)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_message(self, payload: FacebookPublicationPayload, include_url: bool = True) -> str:
        parts: List[str] = [f"\U0001F4F0 {payload.title}"]
        if payload.summary:
            parts.append(f"\n\n{payload.summary[:300]}")
        if payload.hashtags:
            tags = " ".join(
                f"#{t.replace(' ', '_').lower()}" for t in payload.hashtags[:5]
            )
            parts.append(f"\n\n{tags}")
        if include_url and payload.url:
            parts.append(f"\n\n{payload.url}")
        return "".join(parts)

    def _get_best_image(self, payload: FacebookPublicationPayload) -> Optional[str]:
        if not payload.images:
            return None
        return sorted(
            payload.images,
            key=lambda x: (x.get("width", 0) or 0) * (x.get("height", 0) or 0),
            reverse=True,
        )[0].get("url")

    async def _post(self, endpoint: str, data: Dict[str, str], timeout: int = 30) -> Optional[str]:
        url = f"{self.GRAPH_API_BASE}/{self.page_id}/{endpoint}"
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, data=data)
                result = resp.json()
                if resp.status_code == 200 and result.get("id"):
                    logger.info("Facebook post created: %s", result["id"])
                    return result["id"]

                if "error" in result:
                    error = result["error"]
                    code = error.get("code", 0)
                    error_msg = error.get("message", "")
                    logger.warning(
                        "Facebook API error (attempt %d/%d): code=%s msg=%s",
                        attempt, self.max_retries, code, error_msg,
                    )
                    if code in (190, 102) or "token" in error_msg.lower():
                        logger.info("Facebook token expirado, refrescando...")
                        new_token = await self._refresh_token()
                        if new_token:
                            data["access_token"] = new_token
                            continue
                    return None
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "Facebook POST attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except Exception as exc:
                logger.error("Facebook POST unexpected error: %s", exc)
                return None
        return None

    async def _refresh_token(self) -> Optional[str]:
        """Refresca el Page Access Token usando app_id + app_secret."""
        if not self.app_id or not self.app_secret:
            logger.warning(
                "FACEBOOK_APP_ID y FACEBOOK_APP_SECRET requeridos para refresh token"
            )
            return None
        try:
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "fb_exchange_token": self.access_token,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.GRAPH_API_BASE}/oauth/access_token",
                    params=params,
                )
            data = resp.json()
            if data.get("access_token"):
                new_token = data["access_token"]
                await self._save_token(new_token)
                self.access_token = new_token
                logger.info("Facebook token refreshed successfully")
                return new_token
            else:
                logger.error("Facebook token refresh failed: %s", data)
                return None
        except Exception as exc:
            logger.error("Facebook token refresh error: %s", exc)
            return None

    async def _save_token(self, token: str) -> None:
        """Persiste el nuevo token en system_config."""
        try:
            from sqlalchemy import text
            from backend.app.core.database import async_session_factory

            async with async_session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO system_config (key, value, updated_at)
                        VALUES ('facebook_page_token', :val, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = :val, updated_at = NOW()
                    """),
                    {"val": token},
                )
                await session.commit()
            logger.info("Facebook token saved to system_config")
        except Exception as e:
            logger.error("Error saving Facebook token to DB: %s", e)


async def publish_single_news_facebook(news) -> Optional[str]:
    """Publica una noticia en la Facebook Page.

    Consulta si Facebook est\u00e1 configurado. Si no, retorna None sin error.

    Args:
        news: Instancia del modelo News (con title, summary, url, etc.)

    Returns:
        Facebook post ID si se public\u00f3 correctamente, None si no.
    """
    if not settings.facebook_page_id or not settings.facebook_page_token:
        logger.info("Facebook Page no configurado, saltando publicaci\u00f3n")
        return None

    title = news.title or news.original_title or "Sin t\u00edtulo"
    summary = news.summary or news.original_summary or ""

    payload = FacebookPublicationPayload(
        title=title,
        summary=summary[:300] if summary else None,
        url=news.url or "",
        hashtags=list(getattr(news, "hashtags", None) or ["Noticias"]),
        images=list(getattr(news, "images", None) or []),
        news_id=str(news.id),
        published_at=getattr(news, "published_at", None),
        author=getattr(news, "author", None),
    )

    publisher = FacebookPublisher()
    return await publisher.publish(payload)


async def refresh_facebook_token() -> Optional[str]:
    """Refresca el token de Facebook manualmente (usado por el scheduler)."""
    if not settings.facebook_page_id or not settings.facebook_page_token:
        logger.info("Facebook no configurado, saltando refresh token")
        return None
    publisher = FacebookPublisher()
    return await publisher._refresh_token()
