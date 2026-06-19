-- Seed: Google News sources
INSERT INTO sources (name, source_type, config, country, language, priority, is_active)
SELECT * FROM (VALUES
    ('Google News - Perú',    'google_news', '{"keyword":"Perú"}'::jsonb,         'Peru', 'es', 6, true),
    ('Google News - Política', 'google_news', '{"keyword":"Política Perú"}'::jsonb,'Peru', 'es', 5, true),
    ('Google News - Economía', 'google_news', '{"keyword":"Economía Perú"}'::jsonb,'Peru', 'es', 5, true),
    ('Google News - Deportes', 'google_news', '{"keyword":"Deportes Perú"}'::jsonb,'Peru', 'es', 4, true),
    ('Google News - Lima',    'google_news', '{"keyword":"Lima"}'::jsonb,         'Peru', 'es', 4, true)
) AS v(name, source_type, config, country, language, priority, is_active)
WHERE NOT EXISTS (SELECT 1 FROM sources WHERE name = v.name);
