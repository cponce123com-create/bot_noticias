-- seed_sources.sql - Insertar fuentes RSS en la base de datos
INSERT INTO sources (name, source_type, config, country, language, priority, auto_publish, requires_approval, fetch_interval)
SELECT v.name, v.source_type, v.config::jsonb, v.country, v.language, v.priority, v.auto_publish, v.requires_approval, v.fetch_interval
FROM (VALUES
    ('RPP Noticias',       'rss', '{"feed_url":"https://rpp.pe/rss"}'::text,              'Peru', 'es', 10, false, true, 300),
    ('Gestion',            'rss', '{"feed_url":"https://gestion.pe/arcio/rss/"}'::text,    'Peru', 'es', 9, false, true, 300),
    ('El Comercio',        'rss', '{"feed_url":"https://elcomercio.pe/arcio/rss/"}'::text, 'Peru', 'es', 9, false, true, 300),
    ('Andina',             'rss', '{"feed_url":"https://andina.pe/agencia/rss.aspx"}'::text,'Peru', 'es', 10, false, true, 300),
    ('Peru21',             'rss', '{"feed_url":"https://peru21.pe/arcio/rss/"}'::text,     'Peru', 'es', 7, false, true, 300),
    ('La Republica',       'rss', '{"feed_url":"https://larepublica.pe/rss/"}'::text,      'Peru', 'es', 8, false, true, 300),
    ('Depor',              'rss', '{"feed_url":"https://depor.com/arcio/rss/"}'::text,     'Peru', 'es', 6, false, true, 300),
    ('El Bocon',           'rss', '{"feed_url":"https://elbocon.pe/rss/"}'::text,          'Peru', 'es', 5, false, true, 300),
    ('BBC Mundo',          'rss', '{"feed_url":"https://www.bbc.com/mundo/index.xml"}'::text,      'Internacional', 'es', 8, false, true, 300),
    ('Reuters',            'rss', '{"feed_url":"https://www.reutersagency.com/feed/"}'::text,       'Internacional', 'en', 8, false, true, 300),
    ('DW Espanol',         'rss', '{"feed_url":"https://rss.dw.com/rdf/rss-esp-all"}'::text,        'Internacional', 'es', 7, false, true, 300),
    ('France24 Espanol',   'rss', '{"feed_url":"https://www.france24.com/es/rss"}'::text,           'Internacional', 'es', 7, false, true, 300),
    ('El Pais',            'rss', '{"feed_url":"https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"}'::text, 'Internacional', 'es', 7, false, true, 300)
) AS v(name, source_type, config, country, language, priority, auto_publish, requires_approval, fetch_interval)
WHERE NOT EXISTS (SELECT 1 FROM sources s WHERE s.name = v.name AND s.source_type = 'rss');

SELECT count(*) AS fuentes_actuales FROM sources WHERE source_type = 'rss';
