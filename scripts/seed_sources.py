"""Poblar DB con fuentes RSS desde config/sources/rss.yaml.

Uso: nix-shell -p postgresql --run '.venv/bin/python scripts/seed_sources.py'
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg2
import yaml

DSN = "postgresql://neondb_owner:npg_yY1WrIf0xSZB@ep-silent-sound-atcjifon-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require"


def seed():
    yaml_path = Path("config/sources/rss.yaml")
    data = yaml.safe_load(yaml_path.read_text())
    sources = data.get("sources", [])
    print(f"Cargando {len(sources)} fuentes...")

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    cat_map = {
        "general": "politica", "economia": "economia", "deportes": "deportes",
        "tecnologia": "tecnologia", "internacional": "internacional",
        "salud": "salud", "entretenimiento": "entretenimiento",
        "ciencia": "ciencia", "seguridad": "seguridad", "local": "local",
    }

    inserted = 0
    skipped = 0

    for src in sources:
        cur.execute(
            "SELECT id FROM sources WHERE name = %s AND source_type = 'rss'",
            (src["name"],)
        )
        if cur.fetchone():
            print(f"  SKIP: {src['name']}")
            skipped += 1
            continue

        config = json.dumps({"feed_url": src["url"], "fetch_interval": 300})

        cur.execute(
            """INSERT INTO sources (name, source_type, config, country, language,
                                    priority, auto_publish, requires_approval, fetch_interval)
               VALUES (%s, 'rss', %s::jsonb, %s, %s, %s, %s, %s, %s)""",
            (
                src["name"], config, src.get("country", ""),
                src.get("language", "es"), src.get("priority", 5),
                src.get("auto_publish", False),
                src.get("requires_approval", True), 300,
            )
        )
        print(f"  OK: {src['name']}")
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nResumen: {inserted} insertadas, {skipped} omitidas")


if __name__ == "__main__":
    seed()
