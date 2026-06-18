"""Publicador de noticias en Telegram via Bot API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import cloudinary
import cloudinary.uploader
import cloudinary.api
from telegram import Bot, InputMediaPhoto, InputMediaVideo
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut

from backend.app.config import settings

logger = logging.getLogger(__name__)

CATEGORY_EMOJIS: Dict[str, str] = {
    "politica": "\U0001F4F0", "economia": "\U0001F4B0", "deportes": "\u26BD",
    "tecnologia": "\U0001F4BB", "internacional": "\U0001F30D", "salud": "\u2764",
    "entretenimiento": "\U0001F3AC", "ciencia": "\U0001F52C",
    "seguridad": "\U0001F6E1", "local": "\U0001F4CD",
}
DEFAULT_EMOJI = "\U0001F4F0"


@dataclass
class PublicationPayload:
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


class TelegramPublisher:

    def __init__(self) -> None:
        self._token = settings.telegram_bot_token
        if not self._token:
            raise ValueError("TELEGRAM_BOT_TOKEN no configurado")
        self._bot: Optional[Bot] = None
        self.max_retries = 3
        self.base_delay = 2.0
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

    async def _get_bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=self._token)
            await self._bot.initialize()
        return self._bot

    async def publish_text_only(self, chat_id: int, payload: PublicationPayload) -> Optional[int]:
        text = self._build_message(payload)
        return await self._send_message_with_retry(chat_id, text)

    async def publish_with_image(self, chat_id: int, payload: PublicationPayload) -> Optional[int]:
        text = self._build_message(payload)
        image_url = self._get_best_image(payload)
        if image_url:
            return await self._send_photo_with_retry(chat_id, image_url, text)
        return await self.publish_text_only(chat_id, payload)

    async def publish_with_video(self, chat_id: int, payload: PublicationPayload) -> Optional[int]:
        text = self._build_message(payload)
        video_url = self._get_best_video(payload)
        if video_url:
            return await self._send_video_with_retry(chat_id, video_url, text)
        return await self.publish_text_only(chat_id, payload)

    async def publish_album(self, chat_id: int, payload: PublicationPayload) -> Optional[int]:
        text = self._build_message(payload)
        media_group = self._build_media_group(payload, text)
        if not media_group:
            return await self.publish_text_only(chat_id, payload)
        return await self._send_media_group_with_retry(chat_id, media_group)

    def _build_message(self, payload: PublicationPayload) -> str:
        emoji = CATEGORY_EMOJIS.get((payload.category_slug or "").lower(), DEFAULT_EMOJI)
        lines: List[str] = [f"{emoji} *{self._escape_md(payload.title)}*"]
        if payload.summary:
            lines.append("")
            lines.append(self._escape_md(payload.summary))
        if payload.author:
            lines.append("")
            lines.append(f"\u270F {self._escape_md(payload.author)}")
        if payload.url:
            lines.append("")
            lines.append(f"\U0001F517 [Leer mas]({payload.url})")
        if payload.published_at:
            lines.append("")
            lines.append(f"\U0001F552 {payload.published_at.strftime('%d/%m/%Y %H:%M')}")
        if payload.hashtags:
            tags = " ".join(self._escape_md(f"#{tag.replace(' ', '_').lower()}") for tag in payload.hashtags[:5])
            lines.append("")
            lines.append(tags)
        return "\n".join(lines)

    def _get_best_image(self, payload: PublicationPayload) -> Optional[str]:
        if not payload.images:
            return None
        return sorted(payload.images, key=lambda x: (x.get("width", 0) or 0) * (x.get("height", 0) or 0), reverse=True)[0].get("url")

    def _get_best_video(self, payload: PublicationPayload) -> Optional[str]:
        if not payload.videos:
            return None
        return payload.videos[0].get("url")

    def _build_media_group(self, payload: PublicationPayload, caption: str) -> list:
        media = []
        for img in (payload.images or [])[:10]:
            url = img.get("url", "")
            if not url:
                continue
            if self.cloudinary_enabled:
                url = self._upload_to_cloudinary(url, "image") or url
            if not media:
                media.append(InputMediaPhoto(media=url, caption=caption))
            elif len(media) < 10:
                media.append(InputMediaPhoto(media=url))
        if len(media) < 10:
            for vid in (payload.videos or [])[: 10 - len(media)]:
                url = vid.get("url", "")
                if url:
                    media.append(InputMediaVideo(media=url))
        return media

    def _upload_to_cloudinary(self, file_url: str, resource_type: str = "image") -> Optional[str]:
        if not self.cloudinary_enabled:
            return None
        try:
            result = cloudinary.uploader.upload(file_url, resource_type=resource_type, folder="noticiando", quality="auto", fetch_format="auto")
            return result.get("secure_url") or result.get("url")
        except Exception as exc:
            logger.warning("Error subiendo a Cloudinary: %s", exc)
            return None

    async def _send_message_with_retry(self, chat_id: int, text: str) -> Optional[int]:
        bot = await self._get_bot()
        for attempt in range(1, self.max_retries + 1):
            try:
                msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode="MarkdownV2", disable_web_page_preview=True)
                return msg.message_id
            except (TimedOut, NetworkError) as exc:
                logger.warning("send_message intento %d/%d fallo: %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except Forbidden as exc:
                logger.error("Bot bloqueado en chat %d: %s", chat_id, exc)
                return None
            except (BadRequest, TelegramError) as exc:
                logger.error("Error enviando mensaje a %d: %s", chat_id, exc)
                return None
        return None

    async def _send_photo_with_retry(self, chat_id: int, photo_url: str, caption: str) -> Optional[int]:
        bot = await self._get_bot()
        if self.cloudinary_enabled:
            photo_url = self._upload_to_cloudinary(photo_url, "image") or photo_url
        for attempt in range(1, self.max_retries + 1):
            try:
                msg = await bot.send_photo(chat_id=chat_id, photo=photo_url, caption=caption, parse_mode="MarkdownV2")
                return msg.message_id
            except (TimedOut, NetworkError) as exc:
                logger.warning("send_photo intento %d/%d fallo: %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except Forbidden:
                return None
            except (BadRequest, TelegramError) as exc:
                logger.warning("Foto fallo (%s), enviando solo texto", exc)
                return await self._send_message_with_retry(chat_id, caption)
        return None

    async def _send_video_with_retry(self, chat_id: int, video_url: str, caption: str) -> Optional[int]:
        bot = await self._get_bot()
        if self.cloudinary_enabled:
            video_url = self._upload_to_cloudinary(video_url, "video") or video_url
        for attempt in range(1, self.max_retries + 1):
            try:
                msg = await bot.send_video(chat_id=chat_id, video=video_url, caption=caption, parse_mode="MarkdownV2")
                return msg.message_id
            except (TimedOut, NetworkError) as exc:
                logger.warning("send_video intento %d/%d fallo: %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except Forbidden:
                return None
            except (BadRequest, TelegramError) as exc:
                logger.warning("Video fallo, enviando solo texto: %s", exc)
                return await self._send_message_with_retry(chat_id, caption)
        return None

    async def _send_media_group_with_retry(self, chat_id: int, media: list) -> Optional[int]:
        bot = await self._get_bot()
        for attempt in range(1, self.max_retries + 1):
            try:
                msgs = await bot.send_media_group(chat_id=chat_id, media=media)
                return msgs[0].message_id if msgs else None
            except (TimedOut, NetworkError) as exc:
                logger.warning("send_media_group intento %d/%d fallo: %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.base_delay * attempt)
            except RetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
            except Forbidden:
                return None
            except (BadRequest, TelegramError) as exc:
                logger.error("Media group fallo: %s", exc)
                caption = media[0].caption if media else ""
                return await self._send_message_with_retry(chat_id, caption) if caption else None
        return None

    @staticmethod
    def _escape_md(text: str) -> str:
        for ch in r"_*[]()~`>#+-=|{}.!":
            text = text.replace(ch, f"\{ch}")
        return text
