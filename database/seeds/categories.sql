-- =============================================================================
-- Noticiando.pe - Categorias por defecto
-- =============================================================================

INSERT INTO categories (name, slug, description, color, icon, is_active)
VALUES
    ('Política',       'politica',       'Noticias sobre política nacional e internacional',        '#E53935',  'landmark', TRUE),
    ('Economía',       'economia',       'Finanzas, mercados y negocios',                          '#1E88E5',  'trending-up', TRUE),
    ('Deportes',       'deportes',       'Fútbol, vóley y todas las disciplinas deportivas',       '#43A047',  'trophy', TRUE),
    ('Tecnología',     'tecnologia',     'Innovación, startups y mundo digital',                   '#8E24AA',  'cpu', TRUE),
    ('Internacional',  'internacional',  'Sucesos y acontecimientos del mundo',                    '#FB8C00',  'globe', TRUE),
    ('Salud',          'salud',          'Bienestar, medicina y prevención',                       '#00ACC1',  'heart-pulse', TRUE),
    ('Entretenimiento','entretenimiento','Cine, música, tv y cultura pop',                         '#F4511E',  'clapperboard', TRUE),
    ('Ciencia',        'ciencia',        'Investigación, descubrimientos y academia',              '#3949AB',  'flask-conical', TRUE),
    ('Seguridad',      'seguridad',      'Orden público, crimen y protección ciudadana',           '#546E7A',  'shield', TRUE),
    ('Local',          'local',          'Noticias de tu comunidad y región',                      '#6D4C41',  'map-pin', TRUE)
ON CONFLICT (slug) DO NOTHING;
