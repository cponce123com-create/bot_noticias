"""Publica noticias scrapeadas en EPM (El Principe Mestizo) como external headlines.

Usa REST API con API key compartida para autenticacion.
Sigue el mismo patron que TelegramPublisher y FacebookPublisher.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)


class EPMPublisher:
    """Envia noticias scrapeadas a EPM como external_headlines via REST API.

    Autenticacion: X-API-Key header + X-Signature (HMAC-SHA256).
    Dedup por source + link en el lado de EPM.
    Graceful degradation si EPM no responde (no afecta Telegram ni Facebook).
    """

    def __init__(self) -> None:
        self.api_url = settings.epm_api_url.rstrip("/")
        self.api_key = settings.epm_api_key
        self.max_retries = 3
        self.base_delay = 2.0

    async def publish_batch(self, news_items: List[Dict[str, Any]]) -> Dict[str, int]:
        """Envia un lote de noticias a EPM via POST /external-headlines/import.

        Args:
            news_items: Lista de dicts con keys:
                - title / original_title
                - url
                - source_name / author
                - summary / original_summary
                - images (opcional)
                - category_name (opcional)
                - published_at (opcional)

        Returns:
            Dict con: {sent, skipped, errors}
        """
        if not self.api_url or not self.api_key:
            logger.info("EPM no configurado (epm_api_url/epm_api_key)")
            return {"sent": 0, "errors": 0, "skipped": 0}

        if not news_items:
            return {"sent": 0, "errors": 0, "skipped": 0}

        payload: Dict[str, Any] = {
            "headlines": [self._build_headline(item) for item in news_items],
        }

        signature = self._sign_payload(payload)
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "X-Signature": signature,
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{self.api_url}/external-headlines/import",
                        json=payload,
                        headers=headers,
                    )
                data = resp.json()
                if resp.status_code == 200:
                    sent = data.get("sent", 0)
                    skipped = data.get("skipped", 0)
                    errors = data.get("errors", 0)
                    logger.info(
                        "EPM batch: %d enviadas, %d omitidas, %d errores",
                        sent, skipped, errors,
                    )
                    return {"sent": sent, "skipped": skipped, "errors": errors}
                else:
                    logger.warning(
                        "EPM attempt %d/%d: status=%d body=%s",
                        attempt, self.max_retries, resp.status_code, data,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.base_delay * attempt)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "EPM attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except Exception as exc:
                logger.error("EPM unexpected error: %s", exc)
                return {"sent": 0, "errors": 1, "skipped": 0}

        logger.error("EPM batch failed after %d attempts", self.max_retries)
        return {"sent": 0, "errors": 1, "skipped": 0}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_headline(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convierte un item de noticia al formato que espera EPM."""
        pub_date = item.get("published_at") or item.get("fetched_at") or datetime.utcnow()
        if isinstance(pub_date, datetime):
            pub_date = pub_date.isoformat()

        return {
            "title": (item.get("title") or item.get("original_title") or "")[:500],
            "link": (item.get("url") or "")[:1024],
            "source": (item.get("source_name") or item.get("author") or "Noticiando.pe")[:255],
            "summary": (item.get("summary") or item.get("original_summary") or "")[:500],
            "pub_date": pub_date,
            "image_url": self._get_best_image(item) or "",
            "category": (item.get("category_name") or "")[:100],
        }

    def _get_best_image(self, item: Dict[str, Any]) -> Optional[str]:
        images = item.get("images") or []
        if isinstance(images, list) and images:
            if isinstance(images[0], dict):
                return images[0].get("url")
            return str(images[0])
        return None

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        """HMAC-SHA256 signature para verificar integridad."""
        body = json.dumps(payload, sort_keys=True, default=str)
        return hmac.new(
            self.api_key.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()


async def publish_to_epm(news_items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Funcion helper: publica un lote de noticias en EPM.

    Args:
        news_items: Lista de dicts con datos de noticias.

    Returns:
        Dict con: {sent, skipped, errors}
    """
    publisher = EPMPublisher()
    return await publisher.publish_batch(news_items)
