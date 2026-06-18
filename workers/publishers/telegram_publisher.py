"""Publicador de noticias en Telegram via Bot API.

Integra python-telegram-bot para enviar mensajes formateados con
titulo, resumen, enlace, hashtags y medios (imagen/video/album)
subidos a Cloudinary.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cloudinary
import cloudinary.uploader
import cloudinary.api
from telegram import Bot, InputMediaPhoto, InputMediaVideo
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)

from backend.app.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Emojis por categoria (slug o nombre -> emoji)
# ──────────────────────────────────────────────────────────────────────────────
CATEGORY_EMOJIS: Dict[str, str] = {
    "politica": "\U0001F4F0",       # Periódico
    "economia": "\U0001F4B0",       # Bolsa de dinero
    "deportes": "\U000026BD",       # Pelota de fútbol
    "tecnologia": "\U0001F4BB",     # Laptop
    "internacional": "\U0001F30D",  # Globo terráqueo
    "salud": "\U00002764",          # Corazón rojo
    "entretenimiento": "\U0001F3AC",  # Claqueta
    "ciencia": "\U0001F52C",        # Microscopio
    "seguridad": "\U0001F6E1",      # Escudo
    "local": "\U0001F4CD",          # Chincheta
}

DEFAULT_EMOJI = "\U0001F4F0"  # Periódico por defecto


# ──────────────────────────────────────────────────────────────────────────────
# Modelo de datos para una publicacion
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class PublicationPayload:
    """Datos necesarios para publicar una noticia en Telegram."""

    title: str
    summary: Optional[str] = None
    url: Optional[str] = None
    hashtags: List[str] = field(default_factory=list)
    category_slug: Optional[str] = None
    images: List[Dict[str, Any]] = field(default_factory=list)
    videos: List[Dict[str, Any]] = field(default_factory=list)
    news_id: Optional[str] = None
    published_at: Optional[datetime] = None
    author: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Publicador Telegram
# ──────────────────────────────────────────────────────────────────────────────
class TelegramPublisher:
    """Publica noticias en canales de Telegram con formato enriquecido."""

    def __init__(self) -> None:
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN no configurado en el entorno")

        self.bot = Bot(token=settings.telegram_bot_token)
        self.max_retries = 3
        self.base_delay = 2.0

        # Inicializar Cloudinary si hay credenciales
        if settings.cloudinary_cloud_name and settings.cloudinary_api_key and settings.cloudinary_api_secret:
            cloudinary.config(
                cloud_name=settings.cloudinary_cloud_name,
                api_key=settings.cloudinary_api_key,
                api_secret=settings.cloudinary_api_secret,
                secure=True,
            )
            self.cloudinary_enabled = True
        else:
            self.cloudinary_enabled = False
            logger.warning("Cloudinary no configurado; los medios se enviaran como URL directa")

    # ── Metodos de publicacion publicos ──────────────────────────────────────

    async def publish_text_only(
        self, chat_id: int, payload: PublicationPayload,
    ) -> Optional[int]:
        """Publica solo texto (sin medio). Retorna el message_id o None."""
        text = self._build_message(payload)
        return await self._send_message_with_retry(chat_id, text)

    async def publish_with_image(
        self, chat_id: int, payload: PublicationPayload,
    ) -> Optional[int]:
        """Publica texto + una imagen. Retorna el message_id."""
        text = self._build_message(payload)
        image_url = self._get_best_image(payload)
        if image_url:
            return await self._send_photo_with_retry(chat_id, image_url, text)
        return await self.publish_text_only(chat_id, payload)

    async def publish_with_video(
        self, chat_id: int, payload: PublicationPayload,
    ) -> Optional[int]:
        """Publica texto + un video. Retorna el message_id."""
        text = self._build_message(payload)
        video_url = self._get_best_video(payload)
        if video_url:
            return await self._send_video_with_retry(chat_id, video_url, text)
        return await self.publish_text_only(chat_id, payload)

    async def publish_album(
        self, chat_id: int, payload: PublicationPayload,
    ) -> Optional[int]:
        """Publica un album de hasta 10 medios con caption.

        Primero se intenta con imagenes; si no hay, con video;
        si no hay medios, cae a texto solo.
        """
        text = self._build_message(payload)
        media_group = self._build_media_group(payload, text)

        if not media_group:
            return await self.publish_text_only(chat_id, payload)

        return await self._send_media_group_with_retry(chat_id, media_group)

    # ── Construccion del mensaje ─────────────────────────────────────────────

    def _build_message(self, payload: PublicationPayload) -> str:
        """Construye el mensaje formateado en MarkdownV2."""
        emoji = CATEGORY_EMOJIS.get(
            (payload.category_slug or "").lower(), DEFAULT_EMOJI
        )

        parts: List[str] = [
            f"{emoji} *{self._escape_md(payload.title)}*",
        ]

        if payload.summary:
            summary = self._escape_md(payload.summary)
            parts.append(f"
{summary}")

        if payload.author:
            parts.append(f"
\U0000270F {self._escape_md(payload.author)}")

        if payload.url:
            parts.append(f"
\U0001F517 [Leer mas]({payload.url})")

        if payload.published_at:
            time_str = payload.published_at.strftime("%d/%m/%Y %H:%M")
            parts.append(f"
\U0001F552 {time_str}")

        if payload.hashtags:
            tags = " ".join(
                f"#{tag.replace(' ', '_').lower()}" for tag in payload.hashtags[:5]
            )
            parts.append(f"

{tags}")

        return "
".join(parts)

    # ── Manejo de medios ─────────────────────────────────────────────────────

    def _get_best_image(self, payload: PublicationPayload) -> Optional[str]:
        """Retorna la URL de la mejor imagen disponible."""
        if not payload.images:
            return None

        # Preferir la primera imagen con mayor resolucion
        sorted_images = sorted(
            payload.images,
            key=lambda img: (
                (img.get("width") or 0) * (img.get("height") or 0),
                img.get("url", ""),
            ),
            reverse=True,
        )
        return sorted_images[0].get("url")

    def _get_best_video(self, payload: PublicationPayload) -> Optional[str]:
        """Retorna la URL del mejor video disponible."""
        if not payload.videos:
            return None
        return payload.videos[0].get("url")

    def _build_media_group(
        self, payload: PublicationPayload, caption: str,
    ) -> List[InputMediaPhoto | InputMediaVideo]:
        """Construye un grupo de hasta 10 medios para enviar como album."""
        media_group: List[InputMediaPhoto | InputMediaVideo] = []

        # Imagenes primero
        for img in (payload.images or [])[:10]:
            url = img.get("url", "")
            if not url:
                continue

            if self.cloudinary_enabled:
                url = self._upload_to_cloudinary(url, "image") or url

            if not media_group:
                media_group.append(InputMediaPhoto(media=url, caption=caption))
            else:
                if len(media_group) >= 10:
                    break
                media_group.append(InputMediaPhoto(media=url))

        # Videos si aun hay espacio
        if len(media_group) < 10:
            for vid in (payload.videos or [])[: 10 - len(media_group)]:
                url = vid.get("url", "")
                if not url:
                    continue
                media_group.append(InputMediaVideo(media=url))

        return media_group

    # ── Cloudinary ───────────────────────────────────────────────────────────

    def _upload_to_cloudinary(self, file_url: str, resource_type: str = "image") -> Optional[str]:
        """Sube un archivo a Cloudinary y retorna la URL optimizada."""
        if not self.cloudinary_enabled:
            return None
        try:
            result = cloudinary.uploader.upload(
                file_url,
                resource_type=resource_type,
                folder="noticiando",
                quality="auto",
                fetch_format="auto",
            )
            return result.get("secure_url") or result.get("url")
        except Exception as exc:
            logger.warning("Error subiendo a Cloudinary: %s", exc)
            return None

    # ── Envio con reintentos ─────────────────────────────────────────────────

    async def _send_message_with_retry(self, chat_id: int, text: str) -> Optional[int]:
        """Envia un mensaje de texto con reintentos."""
        for attempt in range(1, self.max_retries + 1):
            try:
                msg = await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="MarkdownV2",
                    disable_web_page_preview=True,
                )
                return msg.message_id
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "send_message intento %d/%d fallo: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                logger.warning("Rate limited, esperando %d s", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            except Forbidden as exc:
                logger.error("Bot bloqueado en chat %d: %s", chat_id, exc)
                return None
            except (BadRequest, TelegramError) as exc:
                logger.error("Error enviando mensaje a %d: %s", chat_id, exc)
                return None
        return None

    async def _send_photo_with_retry(
        self, chat_id: int, photo_url: str, caption: str,
    ) -> Optional[int]:
        """Envia una foto con caption y reintentos."""
        # Intentar subir a Cloudinary primero
        if self.cloudinary_enabled:
            uploaded = self._upload_to_cloudinary(photo_url, "image")
            photo_url = uploaded or photo_url

        for attempt in range(1, self.max_retries + 1):
            try:
                msg = await self.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_url,
                    caption=caption,
                    parse_mode="MarkdownV2",
                )
                return msg.message_id
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "send_photo intento %d/%d fallo: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except Forbidden as exc:
                logger.error("Bot bloqueado en chat %d: %s", chat_id, exc)
                return None
            except (BadRequest, TelegramError) as exc:
                # Si falla con foto, reintentar solo texto
                logger.warning("Foto fallo (%s), enviando solo texto", exc)
                return await self._send_message_with_retry(chat_id, caption)
        return None

    async def _send_video_with_retry(
        self, chat_id: int, video_url: str, caption: str,
    ) -> Optional[int]:
        """Envia un video con caption y reintentos."""
        if self.cloudinary_enabled:
            uploaded = self._upload_to_cloudinary(video_url, "video")
            video_url = uploaded or video_url

        for attempt in range(1, self.max_retries + 1):
            try:
                msg = await self.bot.send_video(
                    chat_id=chat_id,
                    video=video_url,
                    caption=caption,
                    parse_mode="MarkdownV2",
                )
                return msg.message_id
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "send_video intento %d/%d fallo: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except Forbidden as exc:
                logger.error("Bot bloqueado en chat %d: %s", chat_id, exc)
                return None
            except (BadRequest, TelegramError) as exc:
                logger.warning("Video fallo (%s), enviando solo texto", exc)
                return await self._send_message_with_retry(chat_id, caption)
        return None

    async def _send_media_group_with_retry(
        self, chat_id: int, media: List[InputMediaPhoto | InputMediaVideo],
    ) -> Optional[int]:
        """Envia un album de medios con reintentos."""
        for attempt in range(1, self.max_retries + 1):
            try:
                msgs = await self.bot.send_media_group(
                    chat_id=chat_id,
                    media=media,
                )
                # Retornar el message_id del primer elemento del album
                return msgs[0].message_id if msgs else None
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "send_media_group intento %d/%d fallo: %s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except Forbidden as exc:
                logger.error("Bot bloqueado en chat %d: %s", chat_id, exc)
                return None
            except (BadRequest, TelegramError) as exc:
                logger.error("Media group fallo: %s", exc)
                # Fallback a solo texto
                caption = media[0].caption if media else ""
                if caption:
                    return await self._send_message_with_retry(chat_id, caption)
                return None
        return None

    # ── Utilidades ───────────────────────────────────────────────────────────

    @staticmethod
    def _escape_md(text: str) -> str:
        """Escapa caracteres especiales de MarkdownV2."""
        special_chars = r"_*[]()~`>#+-=|{}.!"
        for ch in special_chars:
            text = text.replace(ch, f"\{ch}")
        return text

    @staticmethod
    def _emoji_for_category(slug: Optional[str]) -> str:
        """Retorna el emoji correspondiente a una categoria."""
        return CATEGORY_EMOJIS.get((slug or "").lower(), DEFAULT_EMOJI)
