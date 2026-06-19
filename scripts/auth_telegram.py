#!/usr/bin/env python3
"""Autentica Telethon para scrapear canales Telegram.

Uso: .venv/bin/python scripts/auth_telegram.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient

from backend.app.config import settings

SESSION_DIR = Path("data")
SESSION_FILE = SESSION_DIR / "telegram_scraper"


async def main():
    api_id = settings.telegram_api_id
    api_hash = settings.telegram_api_hash
    if not api_id or not api_hash:
        print("❌ Configura TELEGRAM_API_ID y TELEGRAM_API_HASH en .env")
        return

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_FILE), api_id, api_hash)

    await client.start()
    if await client.is_user_authorized():
        print("✅ Ya autenticado!")
    else:
        print("📱 Envia el codigo que Telegram te envio...")
        await client.sign_up()

    me = await client.get_me()
    print(f"✅ Autenticado como: {me.username or me.phone or me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
