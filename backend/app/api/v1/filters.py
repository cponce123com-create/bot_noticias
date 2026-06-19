"""API para gestionar filtros de contenido (config/filters.yaml)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.filters import load_filters, reload_filters
from backend.app.core.security import get_admin_user
from backend.app.models.user import User

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("")
async def list_filters(_current_user: User = Depends(get_admin_user)):
    """Lista todas las categorias y patrones de filtros."""
    return load_filters()


@router.post("/reload")
async def reload_filters_endpoint(_current_user: User = Depends(get_admin_user)):
    """Recarga los filtros desde config/filters.yaml sin reiniciar el servidor."""
    filters = reload_filters()
    categories = sum(len(v) for v in filters.values())
    return {"status": "ok", "categories": len(filters), "patterns": categories}
