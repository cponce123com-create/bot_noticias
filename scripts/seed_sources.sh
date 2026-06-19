#!/usr/bin/env bash
# scripts/seed_sources.sh - Genera y ejecuta SQL para insertar fuentes RSS
set -e

# Cargar DSN desde variable de entorno
DSN="${DATABASE_URL_SYNC:-postgresql://localhost:5432/noticiando}"

cat <<'SQLEOF' | nix-shell -p postgresql --run "psql \"$DSN\""
-- Fuentes RSS Peruanas
INSERT INTO sources (name, source_type, config, country, language, priority, auto_publish, requires_approval, fetch_interval)
SELECT * FROM (VALUES
    ('RPP Noticias',       'rss', '{"feed_url":"https://rpp.pe/rss"}'::jsonb,              'Peru', 'es', 10, false, true, 300),
    ('Gestion',            'rss', '{"feed_url":"https://gestion.pe/arcio/rss/"}'::jsonb,    'Peru', 'es', 9, false, true, 300),
    ('El Comercio',        'rss', '{"feed_url":"https://elcomercio.pe/arcio/rss/"}'::jsonb, 'Peru', 'es', 9, false, true, 300),
    ('Andina',             'rss', '{"feed_url":"https://andina.pe/agencia/rss.aspx"}'::jsonb,'Peru', 'es', 10, false, true, 300),
    ('Peru21',             'rss', '{"feed_url":"https://peru21.pe/arcio/rss/"}'::jsonb,     'Peru', 'es', 7, false, true, 300),
    ('La Republica',       'rss', '{"feed_url":"https://larepublica.pe/rss/"}'::jsonb,      'Peru', 'es', 8, false, true, 300),
    ('Depor',              'rss', '{"feed_url":"https://depor.com/arcio/rss/"}'::jsonb,     'Peru', 'es', 6, false, true, 300),
    ('El Bocón',           'rss', '{"feed_url":"https://elbocon.pe/rss/"}'::jsonb,          'Peru', 'es', 5, false, true, 300),
    ('BBC Mundo',          'rss', '{"feed_url":"https://www.bbc.com/mundo/index.xml"}'::jsonb,      'Internacional', 'es', 8, false, true, 300),
    ('Reuters',            'rss', '{"feed_url":"https://www.reutersagency.com/feed/"}'::jsonb,       'Internacional', 'en', 8, false, true, 300),
    ('DW Espanol',         'rss', '{"feed_url":"https://rss.dw.com/rdf/rss-esp-all"}'::jsonb,        'Internacional', 'es', 7, false, true, 300),
    ('France24 Espanol',   'rss', '{"feed_url":"https://www.france24.com/es/rss"}'::jsonb,           'Internacional', 'es', 7, false, true, 300),
    ('El Pais',            'rss', '{"feed_url":"https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"}'::jsonb, 'Internacional', 'es', 7, false, true, 300)
) AS v(name, source_type, config, country, language, priority, auto_publish, requires_approval, fetch_interval)
WHERE NOT EXISTS (SELECT 1 FROM sources s WHERE s.name = v.name AND s.source_type = 'rss');

SELECT count(*) AS fuentes_insertadas FROM sources WHERE source_type = 'rss';
SQLEOF
