"""Pipeline completo: scrapea RPP, detecta duplicados, inserta en Neon.

Uso: nix-shell -p postgresql --run '.venv/bin/python scripts/test_pipeline.py'
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

import feedparser
import httpx
import psycopg2

DSN = "postgresql://neondb_owner:npg_yY1WrIf0xSZB@ep-silent-sound-atcjifon-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require"


def get_source(conn, name: str):
    cur = conn.cursor()
    cur.execute("SELECT id, config FROM sources WHERE name = %s AND is_active = true", (name,))
    row = cur.fetchone()
    cur.close()
    if row:
        return uuid.UUID(row[0].hex) if isinstance(row[0], uuid.UUID) else uuid.UUID(str(row[0])), row[1]
    return None, None


def scrape_rpp(url: str):
    resp = httpx.get(url, timeout=30, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (NoticiandoBot/1.0)"})
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:15]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        link = (entry.get("link") or "").split("?")[0]  # clean tracking params
        summary = ""
        for tag in ("summary", "description", "subtitle"):
            val = entry.get(tag, "")
            if val:
                summary = val[:300] if isinstance(val, str) else str(val)[:300]
                summary = re.sub(r"<[^>]+>", " ", summary).strip()
                break
        published = None
        for attr in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                try:
                    published = datetime(*parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
                break
        entry_id = entry.get("id") or entry.get("guid") or link
        items.append({
            "external_id": entry_id,
            "url": link,
            "title": title,
            "summary": summary,
            "published": published,
        })
    return items, feed.feed.get("title", "RPP")


def insert_items(conn, source_id: uuid.UUID, items: list):
    cur = conn.cursor()
    new_count = 0
    for item in items:
        # Check dup by URL
        if item["url"]:
            cur.execute("SELECT id FROM news WHERE url = %s LIMIT 1", (item["url"],))
            if cur.fetchone():
                continue
        # Check dup by external_id
        if item["external_id"]:
            cur.execute("SELECT id FROM news WHERE external_id = %s AND source_id = %s LIMIT 1",
                       (item["external_id"], str(source_id)))
            if cur.fetchone():
                continue

        images = json.dumps([])
        cur.execute(
            """INSERT INTO news (source_id, external_id, url, original_title, original_summary,
                                 author, published_at, images, language, status)
               VALUES (%s, %s, %s, %s, %s, '', %s, %s::jsonb, 'es', 'pending_approval')""",
            (str(source_id), item["external_id"], item["url"], item["title"],
             item["summary"], item["published"], images)
        )
        new_count += 1

    # Update last_fetched
    cur.execute("UPDATE sources SET last_fetched_at = NOW(), error_count = 0 WHERE id = %s", (str(source_id),))
    conn.commit()
    cur.close()
    return new_count


def main():
    conn = psycopg2.connect(DSN)
    source_id, config = get_source(conn, "RPP Noticias")
    if not source_id:
        print("Fuente RPP Noticias no encontrada en DB")
        return

    feed_url = config.get("feed_url", "https://rpp.pe/rss")
    print(f"Scrapeando: RPP Noticias ({feed_url})")
    items, feed_title = scrape_rpp(feed_url)
    print(f"  Entradas encontradas: {len(items)}")

    new = insert_items(conn, source_id, items)
    print(f"  Noticias nuevas insertadas: {new}")

    # Mostrar resumen
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM news WHERE source_id = %s", (str(source_id),))
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM news WHERE source_id = %s AND status = 'pending_approval'", (str(source_id),))
    pending = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"  Total en DB: {total} | Pendientes aprobacion: {pending}")
    print("Pipeline completado!")


if __name__ == "__main__":
    main()
