"""Sistema de filtros de contenido para limpieza de noticias.

Los filtros se cargan desde config/filters.yaml y pueden
sobrescribirse via BD (system_config o tabla dedicada).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Ruta al archivo de filtros
FILTERS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "filters.yaml"

# Cache en memoria
_filters_cache: dict[str, list[dict]] | None = None


def load_filters() -> dict[str, list[str]]:
    """Carga los filtros desde config/filters.yaml.

    Returns:
        Dict con categorias y listas de patrones regex.
        Ej: {"tv_streaming": [...], "social_media": [...]}
    """
    global _filters_cache
    if _filters_cache is not None:
        return _filters_cache

    if not FILTERS_PATH.exists():
        logger.warning("Archivo de filtros no encontrado: %s", FILTERS_PATH)
        _filters_cache = {}
        return _filters_cache

    try:
        with open(FILTERS_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Error cargando filtros: %s", e)
        _filters_cache = {}
        return _filters_cache

    _filters_cache = {k: v for k, v in raw.items() if isinstance(v, list)}
    logger.debug("Filtros cargados: %d categorias", len(_filters_cache))
    return _filters_cache


def reload_filters() -> dict[str, list[str]]:
    """Recarga los filtros desde disco (invalida cache)."""
    global _filters_cache
    _filters_cache = None
    return load_filters()


def get_discard_patterns() -> list[re.Pattern]:
    """Retorna patrones compilados para DESCARTAR parrafos (spam)."""
    filters = load_filters()
    patterns = []
    for category in ("tv_streaming", "social_media", "engagement"):
        for pat_str in filters.get(category, []):
            try:
                patterns.append(re.compile(pat_str, re.IGNORECASE))
            except re.error as e:
                logger.warning("Patron invalido [%s]: %s", pat_str, e)
    return patterns


def get_cleanup_patterns() -> list[tuple[re.Pattern, str]]:
    """Retorna pares (pattern, replacement) para LIMPIAR lineas dentro de parrafos.

    Returns:
        Lista de (pattern, replacement) para aplicar con re.sub()
    """
    filters = load_filters()
    result = []
    for pat_str in filters.get("autor_metadata", []):
        try:
            result.append((re.compile(pat_str, re.IGNORECASE), ""))
        except re.error as e:
            logger.warning("Patron invalido [%s]: %s", pat_str, e)
    return result


def apply_filters(paragraphs: list[str]) -> list[str]:
    """Aplica todos los filtros a una lista de parrafos.

    1. Limpia lineas de autoria/metadatos (reemplaza por vacio)
    2. Descarta parrafos que coinciden con patrones de spam
    3. Filtra parrafos muy cortos o vacios

    Args:
        paragraphs: Lista de textos de parrafos extraidos

    Returns:
        Lista de parrafos limpios (max 3)
    """
    discard_patterns = get_discard_patterns()
    cleanup_patterns = get_cleanup_patterns()

    clean = []
    for p in paragraphs:
        if not p:
            continue

        # 1. Limpiar autoria/metadatos (re.sub)
        for pat, repl in cleanup_patterns:
            p = pat.sub(repl, p)
        p = p.strip()

        # 2. Saltar si quedo vacio o es muy corto (< 30 chars)
        if not p or len(p) < 30:
            continue

        # 3. Descartar si coincide con spam
        is_spam = False
        for pat in discard_patterns:
            if pat.search(p):
                is_spam = True
                break
        if is_spam:
            continue

        # 4. Normalizar espacios
        p = re.sub(r"\s+", " ", p).strip()
        clean.append(p)

    return clean[:3]
