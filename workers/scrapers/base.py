"""Clase base abstracta para todos los scrapers del sistema.

Define el contrato (fetch + parse), manejo de reintentos con
backoff exponencial, rotacion de User-Agent, rate limiting y
registro de resultados en ScraperLog.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Pool de 10 User-Agents realistas (escritorio + mobile)
# ──────────────────────────────────────────────────────────────────────────────
USER_AGENTS: List[str] = [
    # Chrome 124 - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox 125 - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Firefox 125 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari 17.4 - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Edge 124 - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome 124 - Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Mobile - Chrome Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    # Mobile - Safari iOS
    "Mozilla/5.0 (iPhone14,3; U; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    # Mobile - Samsung Internet
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) SamsungBrowser/24.0 Chrome/122.0.6261.105 Mobile Safari/537.36",
]


# ──────────────────────────────────────────────────────────────────────────────
# Modelo de datos normalizado para un item extraido
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ScrapedItem:
    """Estructura normalizada que todo scraper debe retornar."""

    external_id: Optional[str] = None
    url: Optional[str] = None
    original_title: Optional[str] = None
    original_summary: Optional[str] = None
    original_body: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    images: List[Dict[str, Any]] = field(default_factory=list)
    videos: List[Dict[str, Any]] = field(default_factory=list)
    language: str = "es"
    hashtags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte el item a diccionario para insertar en la base de datos."""
        return {
            "external_id": self.external_id,
            "url": self.url,
            "original_title": self.original_title,
            "original_summary": self.original_summary,
            "original_body": self.original_body,
            "author": self.author,
            "published_at": self.published_at,
            "images": self.images or [],
            "videos": self.videos or [],
            "language": self.language,
            "hashtags": self.hashtags or [],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Rate Limiter por fuente
# ──────────────────────────────────────────────────────────────────────────────
class RateLimiter:
    """Limita la frecuencia de peticiones a una fuente."""

    def __init__(self, requests_per_minute: int = 20) -> None:
        self.min_interval: float = 60.0 / max(requests_per_minute, 1)
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Espera el tiempo necesario para respetar el limite."""
        async with self._lock:
            elapsed = time.monotonic() - self._last_call
            sleep_time = self.min_interval - elapsed
            if sleep_time > 0:
                logger.debug("Rate limit: esperando %.2fs", sleep_time)
                await asyncio.sleep(sleep_time)
            self._last_call = time.monotonic()


# ──────────────────────────────────────────────────────────────────────────────
# Clase base abstracta
# ──────────────────────────────────────────────────────────────────────────────
class AsyncScraper(ABC):
    """Scraper asincrono base con reintentos, UA rotation y rate limiting."""

    def __init__(
        self,
        source_id: uuid.UUID,
        source_config: Dict[str, Any],
        *,
        max_retries: int = settings.max_scraper_retries,
        base_delay: float = settings.scraper_base_delay,
        requests_per_minute: int = 20,
        timeout: float = 30.0,
    ) -> None:
        self.source_id = source_id
        self.source_config = source_config
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self.rate_limiter = RateLimiter(requests_per_minute)
        self._client: Optional[httpx.AsyncClient] = None

    # ── Metodos abstractos ───────────────────────────────────────────────────

    @abstractmethod
    async def fetch(self) -> bytes:
        """Descarga el contenido crudo de la fuente."""
        ...

    @abstractmethod
    async def parse(self, raw: bytes) -> List[ScrapedItem]:
        """Convierte el contenido crudo en una lista de ScrapedItem."""
        ...

    # ── Ciclo de vida del cliente HTTP ───────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            proxies = None
            if settings.proxy_enabled and settings.proxy_list_parsed:
                proxies = {"all://": random.choice(settings.proxy_list_parsed)}

            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(self.timeout),
                proxy=proxies,  # type: ignore[arg-type]
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "AsyncScraper":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ── Utilidades ───────────────────────────────────────────────────────────

    def _random_ua(self) -> str:
        """Retorna un User-Agent aleatorio del pool."""
        return random.choice(USER_AGENTS)

    def _build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Construye headers con User-Agent rotado."""
        headers: Dict[str, str] = {
            "User-Agent": self._random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        }
        if extra:
            headers.update(extra)
        return headers

    async def _fetch_with_retries(
        self, url: str, extra_headers: Optional[Dict[str, str]] = None
    ) -> bytes:
        """Realiza una peticion HTTP con reintentos y backoff exponencial."""
        await self.rate_limiter.acquire()

        last_exception: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                client = await self._get_client()
                headers = self._build_headers(extra_headers)
                response = await client.get(url, headers=headers)

                # Respuestas exitosas
                if response.status_code == 200:
                    return response.content

                # 429 Too Many Requests - backoff extra
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", str(2**attempt)))
                    logger.warning(
                        "[%s] HTTP 429 - esperando %ds (intento %d/%d)",
                        self.source_id, retry_after, attempt, self.max_retries,
                    )
                    await asyncio.sleep(min(retry_after, 120))
                    continue

                # Errores 5xx recuperables
                if 500 <= response.status_code < 600:
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}", request=response.request, response=response
                    )

                # Cualquier otro codigo no recuperable
                response.raise_for_status()

            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_exception = exc
                delay = min(self.base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1), 60.0)
                logger.warning(
                    "[%s] Intento %d/%d fallo: %s - reintentando en %.1fs",
                    self.source_id, attempt, self.max_retries, exc, delay,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)

        # Todos los reintentos agotados
        raise RuntimeError(
            f"Scraper {self.source_id} agoto {self.max_retries} reintentos. "
            f"Ultimo error: {last_exception}"
        ) from last_exception

    # ── Pipeline completo ────────────────────────────────────────────────────

    async def run(self) -> Dict[str, Any]:
        """Ejecuta fetch + parse y retorna metadatos para el ScraperLog."""
        start = time.monotonic()
        items: List[ScrapedItem] = []
        status = "success"
        error_message: Optional[str] = None

        try:
            raw = await self.fetch()
            items = await self.parse(raw)
            logger.info(
                "[%s] Scraping completado: %d items encontrados",
                self.source_id, len(items),
            )
        except Exception as exc:
            status = "failed"
            error_message = f"{type(exc).__name__}: {exc}"
            logger.error("[%s] Error en scraping: %s", self.source_id, error_message)

        duration_ms = int((time.monotonic() - start) * 1000)

        # Items nuevos (logica externa - aqui solo reportamos encontrados)
        items_new = len(items) if status != "failed" else 0

        # Los items nuevos reales se determinan en el pipeline comparando con DB
        return {
            "source_id": self.source_id,
            "scraper_type": self.__class__.__name__,
            "status": status,
            "items_found": len(items),
            "items_new": items_new,
            "error_message": error_message,
            "duration_ms": duration_ms,
            "metadata": {
                "items_preview": [it.original_title for it in items[:5] if it.original_title],
            },
            "items": items,
        }

    # ── Normalizacion de timestamps ──────────────────────────────────────────

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        """Intenta parsear un timestamp desde varios formatos comunes."""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            for fmt in (
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
                "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822
                "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%d",
            ):
                try:
                    dt = datetime.strptime(value.strip(), fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except (ValueError, AttributeError):
                    continue
        return None
