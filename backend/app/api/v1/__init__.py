from fastapi import APIRouter

from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.categories import router as categories_router
from backend.app.api.v1.news import router as news_router
from backend.app.api.v1.sources import router as sources_router
from backend.app.api.v1.stats import router as stats_router
from backend.app.api.v1.system_config import router as system_config_router
from backend.app.api.v1.telegram_channels import router as telegram_channels_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(sources_router)
v1_router.include_router(categories_router)
v1_router.include_router(news_router)
v1_router.include_router(telegram_channels_router)
v1_router.include_router(stats_router)
v1_router.include_router(system_config_router)

__all__ = ["v1_router"]
