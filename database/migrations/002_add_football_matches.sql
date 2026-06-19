-- 002_add_football_matches.sql
-- Tabla para monitoreo de partidos en vivo

CREATE TABLE IF NOT EXISTS football_matches (
    fixture_id INTEGER PRIMARY KEY,
    home_team VARCHAR(255) NOT NULL,
    away_team VARCHAR(255) NOT NULL,
    home_score INTEGER NOT NULL DEFAULT 0,
    away_score INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'NS',
    minute INTEGER,
    league VARCHAR(255),
    match_date TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_football_matches_status ON football_matches (status);
CREATE INDEX IF NOT EXISTS idx_football_matches_date ON football_matches (match_date DESC);
CREATE INDEX IF NOT EXISTS idx_football_matches_updated ON football_matches (updated_at DESC);

-- Indices adicionales de rendimiento
CREATE INDEX IF NOT EXISTS idx_news_status_date ON news (status, published_at DESC)
WHERE status IN ('pending_approval', 'approved', 'published');

CREATE INDEX IF NOT EXISTS idx_news_url_hash ON news (MD5(url))
WHERE url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sources_last_fetch ON sources (last_fetched_at DESC)
WHERE is_active = TRUE;
