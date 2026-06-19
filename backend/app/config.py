"""
Configuración central de la aplicación usando pydantic-settings.
Variables de entorno cargadas desde .env automáticamente.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database (Neon PostgreSQL) ──
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/noticiando"
    database_url_sync: str = "postgresql://user:pass@localhost:5432/noticiando"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_pre_ping: bool = True

    # ── Telegram Bot (@noticiando_pe_bot) ──
    telegram_bot_token: str = ""
    telegram_admin_id: Optional[str] = None

    # ── Cloudinary ──
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # ── Hugging Face ──
    hf_api_token: str = ""

    # ── Render / Hosting ──
    render_external_url: str = "http://localhost:8000"

    # ── Security ──
    secret_key: str
    access_token_expire_minutes: int = 1440
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Default Admin ──
    admin_email: str = "admin@noticiando.pe"
    admin_password: str

    # ── Timezone ──
    timezone: str = "America/Lima"

    # ── Scraper ──
    default_fetch_interval: int = 300
    max_scraper_retries: int = 5
    scraper_base_delay: float = 1.0
    proxy_enabled: bool = False
    proxy_list: str = ""

    # ── Playwright ──
    playwright_headless: bool = True
    playwright_timeout: int = 30000

    # ── Scheduler ──
    enable_scheduler: bool = True
    scheduler_sources_interval: int = 5
    scheduler_cleanup_interval: int = 1440
    scheduler_backup_interval: int = 43200

    # ── Database — Migrations ──
    run_migrations: bool = True

    # ── Logging ──
    log_level: str = "INFO"
    log_format: str = "json"

    # ── Paths ──
    media_dir: Path = Path("media")
    images_dir: Path = Path("media/images")
    videos_dir: Path = Path("media/videos")

    @property
    def proxy_list_parsed(self) -> List[str]:
        if not self.proxy_list:
            return []
        return [p.strip() for p in self.proxy_list.split(",") if p.strip()]

    # ── APIs externas ──
    football_api_key: str = ""
    weather_api_key: str = ""
    exchange_api_key: str = ""

    @model_validator(mode="after")
    def _ensure_media_dirs(self) -> "Settings":
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        if not self.secret_key:
            raise ValueError("SECRET_KEY no configurada")
        if not self.admin_password:
            raise ValueError("ADMIN_PASSWORD no configurada")
        return self


settings = Settings()
