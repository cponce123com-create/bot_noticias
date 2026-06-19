-- =============================================================================
-- Noticiando.pe - Esquema completo de base de datos PostgreSQL
-- Version: 0.1.0
-- Requiere: PostgreSQL 15+ con pgvector
-- =============================================================================

-- === Extensiones ===
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- 1. USUARIOS
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username    VARCHAR(100) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role        VARCHAR(20) NOT NULL DEFAULT 'editor',
    telegram_id BIGINT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    last_login  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_user_role CHECK (role IN ('admin', 'editor', 'moderator'))
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_telegram_id ON users (telegram_id) WHERE telegram_id IS NOT NULL;


-- =============================================================================
-- 2. CATEGORIAS
-- =============================================================================
CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(100) NOT NULL,
    description TEXT,
    color       VARCHAR(7),
    icon        VARCHAR(50),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_categories_name UNIQUE (name),
    CONSTRAINT uq_categories_slug UNIQUE (slug)
);


-- =============================================================================
-- 3. FUENTES (RSS, Web, Telegram, etc.)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sources (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    source_type     VARCHAR(20) NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    country         VARCHAR(100),
    language        VARCHAR(10) NOT NULL DEFAULT 'es',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_paused       BOOLEAN NOT NULL DEFAULT FALSE,
    last_fetched_at TIMESTAMPTZ,
    fetch_interval  INTEGER NOT NULL DEFAULT 300,
    error_count     INTEGER NOT NULL DEFAULT 0,
    max_errors      INTEGER NOT NULL DEFAULT 10,
    cooldown_until  TIMESTAMPTZ,
    priority        INTEGER NOT NULL DEFAULT 5,
    auto_publish    BOOLEAN NOT NULL DEFAULT FALSE,
    requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
    target_channels BIGINT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,

    CONSTRAINT ck_source_type CHECK (
        source_type IN ('rss', 'web', 'telegram_channel', 'telegram_group', 'twitter', 'youtube')
    )
);

CREATE INDEX idx_sources_type ON sources (source_type);
CREATE INDEX idx_sources_active ON sources (is_active) WHERE is_active = TRUE;
CREATE INDEX idx_sources_cooldown ON sources (cooldown_until) WHERE cooldown_until IS NOT NULL;
CREATE INDEX idx_sources_priority ON sources (priority DESC, fetch_interval ASC);


-- =============================================================================
-- 4. NOTICIAS
-- =============================================================================
CREATE TABLE IF NOT EXISTS news (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id           UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    external_id         VARCHAR(500),
    url                 VARCHAR(2048),
    original_title      TEXT,
    original_summary    TEXT,
    original_body       TEXT,
    author              VARCHAR(255),
    title               VARCHAR(80),
    summary             VARCHAR(300),
    body                TEXT,
    hashtags            TEXT[],
    category_id         INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    category_confidence REAL,
    is_clickbait        BOOLEAN NOT NULL DEFAULT FALSE,
    is_spam             BOOLEAN NOT NULL DEFAULT FALSE,
    sentiment           VARCHAR(20),
    images              JSONB NOT NULL DEFAULT '[]'::jsonb,
    videos              JSONB NOT NULL DEFAULT '[]'::jsonb,
    published_at        TIMESTAMPTZ,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    language            VARCHAR(10) NOT NULL DEFAULT 'es',
    status              VARCHAR(30) NOT NULL DEFAULT 'ingested',
    reviewed_by         UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at         TIMESTAMPTZ,
    review_notes        TEXT,
    published_to_tg     BIGINT[],
    telegram_msg_ids    BIGINT[],
    duplicate_of        UUID REFERENCES news(id) ON DELETE SET NULL,
    similarity_score    REAL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_news_status CHECK (
        status IN (
            'ingested', 'duplicate', 'cleaned', 'classified',
            'summarized', 'media_ready', 'pending_approval',
            'approved', 'rejected', 'published', 'failed'
        )
    )
);

-- Indices principales para busqueda y listado
CREATE INDEX idx_news_source_id ON news (source_id);
CREATE INDEX idx_news_status ON news (status);
CREATE INDEX idx_news_category_id ON news (category_id);
CREATE INDEX idx_news_published_at ON news (published_at DESC);
CREATE INDEX idx_news_fetched_at ON news (fetched_at DESC);
CREATE INDEX idx_news_language ON news (language);
CREATE INDEX idx_news_duplicate_of ON news (duplicate_of) WHERE duplicate_of IS NOT NULL;
CREATE INDEX idx_news_external_id ON news (source_id, external_id) WHERE external_id IS NOT NULL;

-- Indice compuesto para el pipeline de aprobacion
CREATE INDEX idx_news_pipeline ON news (status, published_at DESC NULLS LAST)
    WHERE status IN ('pending_approval', 'approved', 'classified');

-- Indice funcional para busqueda textual (FTS con configuracion espanol)
CREATE INDEX idx_news_fts ON news
    USING GIN (to_tsvector('spanish', coalesce(title, '') || ' ' || coalesce(summary, '')));


-- =============================================================================
-- 5. CANALES DE TELEGRAM
-- =============================================================================
CREATE TABLE IF NOT EXISTS telegram_channels (
    id           SERIAL PRIMARY KEY,
    chat_id      BIGINT NOT NULL,
    channel_name VARCHAR(255),
    channel_type VARCHAR(20) NOT NULL DEFAULT 'channel',
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    config       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_telegram_chat_id UNIQUE (chat_id),
    CONSTRAINT ck_channel_type CHECK (channel_type IN ('channel', 'group', 'supergroup'))
);

CREATE INDEX idx_telegram_channels_active ON telegram_channels (is_active) WHERE is_active = TRUE;


-- =============================================================================
-- 6. LOGS DE PUBLICACION
-- =============================================================================
CREATE TABLE IF NOT EXISTS publication_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    news_id         UUID NOT NULL REFERENCES news(id) ON DELETE CASCADE,
    channel_id      BIGINT NOT NULL,
    telegram_msg_id BIGINT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message   TEXT,
    published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT ck_pub_status CHECK (status IN ('pending', 'sent', 'failed', 'deleted'))
);

CREATE INDEX idx_pub_logs_news_id ON publication_logs (news_id);
CREATE INDEX idx_pub_logs_channel_id ON publication_logs (channel_id);
CREATE INDEX idx_pub_logs_status ON publication_logs (status);
CREATE INDEX idx_pub_logs_published_at ON publication_logs (published_at DESC);


-- =============================================================================
-- 7. COLA DE APROBACION
-- =============================================================================
CREATE TABLE IF NOT EXISTS approval_queue (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    news_id     UUID NOT NULL REFERENCES news(id) ON DELETE CASCADE,
    priority    INTEGER NOT NULL DEFAULT 5,
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_approval_status CHECK (status IN ('pending', 'approved', 'rejected', 'editing'))
);

CREATE INDEX idx_approval_queue_news_id ON approval_queue (news_id);
CREATE INDEX idx_approval_queue_status ON approval_queue (status);
CREATE INDEX idx_approval_queue_assigned_to ON approval_queue (assigned_to) WHERE assigned_to IS NOT NULL;
CREATE INDEX idx_approval_queue_priority ON approval_queue (priority DESC, created_at ASC)
    WHERE status = 'pending';


-- =============================================================================
-- 8. LOGS DE SCRAPER
-- =============================================================================
CREATE TABLE IF NOT EXISTS scraper_logs (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id    UUID REFERENCES sources(id) ON DELETE SET NULL,
    scraper_type VARCHAR(20) NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'success',
    items_found  INTEGER NOT NULL DEFAULT 0,
    items_new    INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    duration_ms  INTEGER,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_scraper_status CHECK (status IN ('success', 'partial', 'failed'))
);

CREATE INDEX idx_scraper_logs_source_id ON scraper_logs (source_id);
CREATE INDEX idx_scraper_logs_status ON scraper_logs (status);
CREATE INDEX idx_scraper_logs_created_at ON scraper_logs (created_at DESC);
CREATE INDEX idx_scraper_logs_source_date ON scraper_logs (source_id, created_at DESC);


-- =============================================================================
-- 9. CONFIGURACION DEL SISTEMA (KV Store)
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_config (
    key         VARCHAR(100) PRIMARY KEY,
    value       JSONB NOT NULL,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by  UUID REFERENCES users(id) ON DELETE SET NULL
);


-- =============================================================================
-- 10. EVENTOS DE ANALITICA
-- =============================================================================
CREATE TABLE IF NOT EXISTS analytics_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type  VARCHAR(50) NOT NULL,
    source_id   UUID REFERENCES sources(id) ON DELETE SET NULL,
    news_id     UUID REFERENCES news(id) ON DELETE SET NULL,
    data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analytics_event_type ON analytics_events (event_type);
CREATE INDEX idx_analytics_source_id ON analytics_events (source_id) WHERE source_id IS NOT NULL;
CREATE INDEX idx_analytics_news_id ON analytics_events (news_id) WHERE news_id IS NOT NULL;
CREATE INDEX idx_analytics_created_at ON analytics_events (created_at DESC);
CREATE INDEX idx_analytics_event_type_date ON analytics_events (event_type, created_at DESC);


-- =============================================================================
-- FUNCION: Actualizar updated_at automaticamente
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_users_updated_at') THEN
        CREATE TRIGGER trg_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sources_updated_at') THEN
        CREATE TRIGGER trg_sources_updated_at
            BEFORE UPDATE ON sources
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_news_updated_at') THEN
        CREATE TRIGGER trg_news_updated_at
            BEFORE UPDATE ON news
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_approval_queue_updated_at') THEN
        CREATE TRIGGER trg_approval_queue_updated_at
            BEFORE UPDATE ON approval_queue
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END;
$$

-- Migraciones adicionales
\i database/migrations/002_add_football_matches.sql
