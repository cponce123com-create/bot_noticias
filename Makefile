# ==============================================================================
# Noticiando.pe - Makefile
# Comandos comunes para desarrollo local
# ==============================================================================

.PHONY: install dev lint format db-init db-migrate db-upgrade check test clean

# ── Variables ──────────────────────────────────────────────────────────────
PYTHON    := python3
PIP       := $(PYTHON) -m pip
RUFF      := ruff
MYPY      := mypy
PYTEST    := $(PYTHON) -m pytest
ALEMBIC   := $(PYTHON) -m alembic
UVICORN   := $(PYTHON) -m uvicorn

# ── Instalacion ────────────────────────────────────────────────────────────
install:                   ## Instalar dependencias del proyecto
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	$(PIP) install pre-commit
	pre-commit install 2>/dev/null || true

install-prod:              ## Instalar solo dependencias de produccion
	$(PIP) install --upgrade pip
	$(PIP) install -e .

# ── Desarrollo ──────────────────────────────────────────────────────────────
dev:                       ## Iniciar servidor de desarrollo (FastAPI + recarga)
	$(UVICORN) backend.app.main:app 
		--reload 
		--host 0.0.0.0 
		--port 8000 
		--log-level info

dev-workers:               ## Iniciar workers (scrapers + scheduler) en modo desarrollo
	$(PYTHON) -m workers.scheduler.main

# ── Calidad de codigo ───────────────────────────────────────────────────────
lint:                      ## Ejecutar linters (ruff check + mypy)
	$(RUFF) check . --fix --show-fixes
	$(MYPY) backend/ workers/ --ignore-missing-imports

format:                    ## Formatear codigo con ruff
	$(RUFF) format .
	$(RUFF) check --fix-only .

check: lint                ## Alias para lint (pre-commit CI friendly)

# ── Base de datos ──────────────────────────────────────────────────────────
db-init:                   ## Inicializar la base de datos (esquema completo + seeds)
	psql "$(DATABASE_URL_SYNC)" -f database/init.sql
	psql "$(DATABASE_URL_SYNC)" -f database/seeds/categories.sql
	psql "$(DATABASE_URL_SYNC)" -f database/seeds/admin_user.sql

db-migrate:                ## Crear nueva migracion de Alembic
	$(ALEMBIC) revision --autogenerate -m "$(message)"

db-upgrade:                ## Aplicar migraciones pendientes
	$(ALEMBIC) upgrade head

db-downgrade:              ## Revertir ultima migracion
	$(ALEMBIC) downgrade -1

db-reset:                  ## Resetear base de datos (drop + init + migrate)
	$(ALEMBIC) downgrade base 2>/dev/null || true
	$(PYTHON) -c "from backend.app.core.database import Base, engine; Base.metadata.drop_all(engine)"
	$(ALEMBIC) upgrade head
	psql "$(DATABASE_URL_SYNC)" -f database/seeds/categories.sql
	psql "$(DATABASE_URL_SYNC)" -f database/seeds/admin_user.sql

# ── Tests ──────────────────────────────────────────────────────────────────
test:                      ## Ejecutar tests
	$(PYTEST) tests/ -v --cov=backend --cov=workers --cov-report=term-missing

test-unit:                 ## Ejecutar solo tests unitarios
	$(PYTEST) tests/unit/ -v

test-integration:          ## Ejecutar solo tests de integracion
	$(PYTEST) tests/integration/ -v --cov=backend

test-file:                 ## Ejecutar un archivo de test especifico
	$(PYTEST) tests/$(file) -v

# ── Utilidades ────────────────────────────────────────────────────────────
clean:                     ## Limpiar archivos temporales y caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ 2>/dev/null || true
	rm -rf build/ dist/ 2>/dev/null || true
	@echo "Limpieza completada."

help:                      ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) 
		| sort 
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s
", $$1, $$2}'

.DEFAULT_GOAL := help
