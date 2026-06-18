"""Runner maestro - Scrapea todas las fuentes y publica en Telegram.

Uso:
  .venv/bin/python scripts/run.py                # Un ciclo completo
  .venv/bin/python scripts/run.py --watch         # Ciclo continuo cada 5 min

Requiere: nix-shell -p postgresql zlib stdenv.cc.cc.lib --run '...'
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import httpx
import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("runner")

DSN = "postgresql://neondb_owner:npg_yY1WrIf0xSZB@ep-silent-sound-atcjifon-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require"
ADMIN_CHAT_ID = 6922534707

# ── Categorias por keywords ─────────────────────────────────────────────────
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "politica": ["presidente", "congreso", "gobierno", "ministerio", "elecciones",
                  "partido", "senado", "diputado", "municipal", "ministro",
                  "dina baluarte", "presidencial", "votacion", "parlamento"],
    "economia": ["economia", "empresa", "mercado", "dolar", "inflacion", "pbi",
                 "inversion", "banco", "finanzas", "bolsa", "comercio",
                 "presupuesto", "impuesto", "exportacion", "tipo de cambio"],
    "deportes": ["futbol", "deporte", "mundial", "liga", "partido", "gol",
                  "campeonato", "seleccion", "tenis", "baloncesto", "voley",
                  "boxeo", "atletismo", "juegos olimpicos"],
    "tecnologia": ["tecnologia", "digital", "internet", "inteligencia artificial",
                   "software", "app", "celular", "robot", "startup", "datos",
                   "ciber", "ia", "redes sociales", "whatsapp"],
    "internacional": ["internacional", "mundo", "global", "eeuu", "china",
                      "rusia", "europa", "naciones unidas", "otan", "guerra",
                      "conflicto", "diplomatico", "embajador"],
    "salud": ["salud", "hospital", "medico", "enfermedad", "vacuna", "covid",
              "paciente", "clinica", "tratamiento", "medicamento", "seguro"],
    "entretenimiento": ["espectaculo", "cine", "musica", "television", "artista",
                        "concierto", "pelicula", "farandula", "famoso", "show"],
    "ciencia": ["ciencia", "investigacion", "descubrimiento", "espacio", "nasa",
                "arqueologia", "fosil", "piramide", "laboratorio", "academico"],
    "seguridad": ["seguridad", "delito", "robo", "crimen", "policia", "violencia",
                  "asesinato", "extorsion", "narcotrafico", "sicariato"],
    "local": ["regional", "provincia", "distrito", "alcalde", "municipalidad",
              "comunidad", "local", "departamento"],
}

DEFAULT_CATEGORY = "politica"

CATEGORY_EMOJIS = {
    "politica": "\U0001F4F0", "economia": "\U0001F4B0", "deportes": "\u26BD",
    "tecnologia": "\U0001F4BB", "internacional": "\U0001F30D", "salud": "\u2764",
    "entretenimiento": "\U0001F3AC", "ciencia": "\U0001F52C",
    "seguridad": "\U0001F6E1", "local": "\U0001F4CD",
}

CATEGORY_NAMES = {
    "politica": "Politica", "economia": "Economia", "deportes": "Deportes",
    "tecnologia": "Tecnologia", "internacional": "Internacional",
    "salud": "Salud", "entretenimiento": "Entretenimiento",
    "ciencia": "Ciencia", "seguridad": "Seguridad", "local": "Local",
}


def get_sources() -> List[Tuple[uuid.UUID, str, str, str]]:
    """Retorna fuentes activas: (id, name, feed_url, country)."""
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, config->>'feed_url' as url, country
        FROM sources
        WHERE source_type = 'rss' AND is_active = true AND is_paused = false
          AND (cooldown_until IS NULL OR cooldown_until < NOW())
          AND error_count < max_errors
        ORDER BY priority DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [(uuid.UUID(str(r[0])), r[1], r[2], r[3]) for r in rows]


def classify_news(title: str, summary: str) -> Tuple[str, float]:
    """Clasifica una noticia por keywords. Retorna (slug, confidence)."""
    text = f"{title} {summary}".lower()
    scores: Dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score
    if not scores:
        return DEFAULT_CATEGORY, 0.0
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = round(scores[best] / total, 2) if total > 0 else 0.0
    return best, confidence


def generate_hashtags(title: str, summary: str, source_name: str, category_slug: str) -> List[str]:
    """Genera hashtags basados en el contenido."""
    tags = set()
    tags.add(CATEGORY_NAMES.get(category_slug, "Noticias"))
    country_map = {
        "Peru": "Peru", "Internacional": "Mundo",
        "Argentina": "Argentina", "Colombia": "Colombia", "Mexico": "Mexico",
    }
    source_upper = source_name.upper()
    for country, tag in country_map.items():
        if country in source_name or country.upper() in source_upper:
            tags.add(tag)
            break
    # Extraer palabras clave del titulo
    stopwords = {"el", "la", "los", "las", "un", "una", "en", "de", "del", "y",
                 "a", "con", "por", "para", "se", "su", "que", "es", "no"}
    words = re.findall(r'\b[A-Z][a-z]{3,}\b', title)
    for word in words[:3]:
        if word.lower() not in stopwords:
            tags.add(word)
    return list(tags)[:5]


def scrape_source(feed_url: str, max_items: int = 20) -> List[Dict[str, Any]]:
    """Scrapea un feed RSS."""
    try:
        resp = httpx.get(
            feed_url, timeout=30, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (NoticiandoBot/1.0; +https://noticiando.pe)"},
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("  HTTP error: %s", exc)
        return []

    feed = feedparser.parse(resp.content)
    items = []

    for entry in feed.entries[:max_items]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue

        link = (entry.get("link") or "").split("?")[0]

        summary = ""
        for tag in ("summary", "description", "subtitle"):
            val = entry.get(tag, "")
            if val:
                summary = val[:500] if isinstance(val, str) else str(val)[:500]
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

        images = []
        for mc in (entry.get("media_content", []) or [])[:3]:
            if isinstance(mc, dict) and mc.get("url"):
                images.append({"url": mc["url"]})

        if not images:
            summary_html = entry.get("summary", "") or ""
            img_match = re.search(r'<img[^>]+src=([\"\'])(https?://[^\"\']+)\1', summary_html)
            if img_match:
                images.append({"url": img_match.group(1)})

        entry_id = entry.get("id") or entry.get("guid") or link or title

        items.append({
            "external_id": str(entry_id)[:500],
            "url": link,
            "title": title[:500],
            "summary": summary[:500],
            "published": published,
            "images": images,
        })

    return items


def dedup_and_insert(conn, source_id: uuid.UUID, items: List[Dict], source_name: str) -> List[Dict]:
    """Inserta items no duplicados y retorna los nuevos."""
    cur = conn.cursor()
    new_items = []

    for item in items:
        # Check URL
        if item["url"]:
            cur.execute("SELECT id FROM news WHERE url = %s LIMIT 1", (item["url"],))
            if cur.fetchone():
                continue

        # Check external_id
        if item["external_id"]:
            cur.execute(
                "SELECT id FROM news WHERE external_id = %s AND source_id = %s LIMIT 1",
                (item["external_id"], str(source_id)),
            )
            if cur.fetchone():
                continue

        # Clasificar
        cat_slug, confidence = classify_news(item["title"], item["summary"])
        cat_name = CATEGORY_NAMES.get(cat_slug, "Politica")

        # Hashtags
        hashtags = generate_hashtags(item["title"], item["summary"], source_name, cat_slug)

        # Generar titulo limpio (max 80 chars) y resumen (max 300 chars)
        title_clean = item["title"][:80]
        summary_clean = item["summary"][:300]

        # Imagenes
        images_json = json.dumps(item["images"])

        cur.execute(
            """INSERT INTO news (source_id, external_id, url, original_title, original_summary,
                                 title, summary, author, published_at, images, language,
                                 category_id, hashtags, status)
               SELECT %s, %s, %s, %s, %s,
                      %s, %s, '', %s, %s::jsonb, 'es',
                      c.id, %s::text[], 'pending_approval'
               FROM categories c WHERE c.slug = %s
               """,
            (
                str(source_id), item["external_id"], item["url"],
                item["title"], item["summary"],
                title_clean, summary_clean, item["published"],
                images_json, hashtags, cat_slug,
            ),
        )
        new_items.append({**item, "category_slug": cat_slug, "hashtags": hashtags})

    # Update last_fetched
    cur.execute("UPDATE sources SET last_fetched_at = NOW(), error_count = 0 WHERE id = %s", (str(source_id),))
    conn.commit()
    cur.close()

    return new_items


async def publish_news(news_items: List[Dict], source_name: str, chat_id: int = ADMIN_CHAT_ID) -> int:
    """Publica una lista de noticias en Telegram."""
    if not news_items:
        return 0

    from backend.app.config import settings
    settings.telegram_bot_token = "8807852904:AAHLeIw0tJXqBSOFEoLrr3PFDF99UrdGs-E"
    settings.cloudinary_cloud_name = "dicudg2ok"
    settings.cloudinary_api_key = "528278259254476"
    settings.cloudinary_api_secret = "t_XiSjyrWLXUavZ5KjoorhxAs-8"
    settings.telegram_admin_id = str(ADMIN_CHAT_ID)

    from workers.publishers.telegram_publisher import TelegramPublisher, PublicationPayload

    pub = TelegramPublisher()
    await pub._get_bot()

    published = 0
    for item in news_items:
        payload = PublicationPayload(
            title=item["title"][:80],
            summary=item["summary"][:300],
            url=item.get("url", ""),
            hashtags=item.get("hashtags", [source_name]),
            category_slug=item.get("category_slug", ""),
            published_at=item.get("published") or datetime.now(),
            author=source_name,
            images=item.get("images", []),
        )

        try:
            if item.get("images"):
                msg_id = await pub.publish_with_image(chat_id=chat_id, payload=payload)
            else:
                msg_id = await pub.publish_text_only(chat_id=chat_id, payload=payload)

            if msg_id:
                published += 1
        except Exception as exc:
            logger.warning("  Error publicando: %s", exc)

    return published


def run_all_sources(publish: bool = True) -> Dict[str, Any]:
    """Ejecuta el pipeline completo para todas las fuentes."""
    start = time.time()
    sources = get_sources()
    logger.info("=" * 60)
    logger.info("RUNNER: %d fuentes activas", len(sources))
    logger.info("=" * 60)

    total_new = 0
    total_published = 0
    results: List[Dict] = []

    for src_id, name, feed_url, country in sources:
        logger.info("[%s] Scrapeando...", name)
        items = scrape_source(feed_url)
        if not items:
            logger.info("  Sin entradas")
            continue

        logger.info("  %d entradas encontradas", len(items))

        conn = psycopg2.connect(DSN)
        new_items = dedup_and_insert(conn, src_id, items, name)
        conn.close()

        if not new_items:
            logger.info("  Sin noticias nuevas")
            continue

        logger.info("  %d NUEVAS: %s", len(new_items),
                     ", ".join(n["title"][:40] for n in new_items[:3]))

        total_new += len(new_items)

        if publish:
            count = asyncio.run(publish_news(new_items, name))
            total_published += count
            logger.info("  Publicadas: %d", count)

        results.append({"source": name, "found": len(items), "new": len(new_items)})

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info("RESUMEN: %d nuevas | %d publicadas | %.1fs", total_new, total_published, elapsed)
    logger.info("=" * 60)

    return {
        "sources": len(sources),
        "total_new": total_new,
        "total_published": total_published,
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
    }


def watch_loop(interval_minutes: int = 5):
    """Ejecuta el pipeline en loop continuo."""
    logger.info("MODO WATCH: cada %d minutos", interval_minutes)
    while True:
        try:
            run_all_sources(publish=True)
        except Exception as exc:
            logger.error("Error en ciclo: %s", exc)
        logger.info("Durmiendo %d min...", interval_minutes)
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch_loop()
    else:
        run_all_sources(publish=True)
