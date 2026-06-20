"""Aprueba y publica noticias pendientes en Telegram.

Uso: nix-shell -p postgresql zlib stdenv.cc.cc.lib --run '.venv/bin/python scripts/publish_pending.py'
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.config import settings
DSN = settings.database_url_sync
ADMIN_CHAT_ID = 6922534707


async def publish():
    from backend.app.config import settings

    from workers.publishers.telegram_publisher import TelegramPublisher, PublicationPayload

    pub = TelegramPublisher()
    bot = await pub._get_bot()

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    # Obtener noticias pendientes con info de la fuente y categoria
    cur.execute("""
        SELECT n.id, n.original_title, n.original_summary, n.url,
               n.images, n.published_at, n.author, n.language,
               s.name as source_name, c.slug as cat_slug
        FROM news n
        JOIN sources s ON s.id = n.source_id
        LEFT JOIN categories c ON c.id = n.category_id
        WHERE n.status = 'pending_approval'
        ORDER BY n.fetched_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    if not rows:
        print("No hay noticias pendientes")
        cur.close()
        conn.close()
        return

    print(f"Publicando {len(rows)} noticias...")

    published_count = 0
    for row in rows:
        news_id, title, summary, url, images_json, pub_date, author, lang, source_name, cat_slug = row

        title = (title or "")[:80]
        summary = (summary or "")[:300]

        # Parse images
        images = []
        try:
            imgs = json.loads(images_json) if isinstance(images_json, str) else (images_json or [])
            images = [{"url": img["url"]} for img in imgs[:3] if img.get("url")]
        except Exception:
            pass

        payload = PublicationPayload(
            title=title,
            summary=summary,
            url=url or "",
            hashtags=[source_name.replace(" ", ""), "Noticias"],
            category_slug=cat_slug or "",
            published_at=pub_date or datetime.now(),
            author=author or source_name,
            images=images,
        )

        try:
            if images:
                msg_id = await pub.publish_with_image(chat_id=ADMIN_CHAT_ID, payload=payload)
            else:
                msg_id = await pub.publish_text_only(chat_id=ADMIN_CHAT_ID, payload=payload)

            if msg_id:
                # Marcar como publicada
                cur.execute(
                    "UPDATE news SET status = 'published', published_to_tg = %s WHERE id = %s",
                    ([ADMIN_CHAT_ID], news_id)
                )
                published_count += 1
                print(f"  [{published_count}] OK: {title[:50]}... (msg_id={msg_id})")
            else:
                print(f"  FALL: {title[:50]}... (sin response)")

        except Exception as exc:
            print(f"  ERROR: {title[:50]}... - {exc}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nPublicadas: {published_count}/{len(rows)}")


if __name__ == "__main__":
    asyncio.run(publish())
