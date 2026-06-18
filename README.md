# Noticiando.pe — Bot de Agregación de Noticias para Telegram

**@noticiando_pe_bot** — Plataforma profesional de agregación de noticias que recopila información automáticamente desde múltiples fuentes y la publica en Telegram.

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| **API** | FastAPI + Python 3.11 |
| **DB** | PostgreSQL 16 + pgvector (Neon) |
| **Media** | Cloudinary (25GB free) |
| **AI** | Hugging Face Inference API (free) |
| **Scheduler** | APScheduler (sin Redis) |
| **Telegram** | python-telegram-bot + Telethon |
| **Frontend** | React + Vite + Tailwind (próximamente) |
| **Hosting** | Render Web Service + Render Cron |

## Estructura del Proyecto

```
botnoticias/
├── backend/          # FastAPI + ORM + Schemas + API routes
│   └── app/
│       ├── api/v1/   # Auth, Sources, Categories, News endpoints
│       ├── core/     # Database, Security, Config
│       ├── models/   # SQLAlchemy ORM (10 modelos)
│       └── schemas/  # Pydantic validators
├── workers/
│   ├── scrapers/     # RSS, Web (Playwright), Telegram monitor
│   ├── pipeline/     # Deduplicator, Classifier, Summarizer
│   └── publishers/   # Telegram Publisher (Cloudinary integration)
├── ai/               # Sentence Transformers, Zero-shot classification
├── database/
│   ├── init.sql      # Schema completo con pgvector + índices
│   └── seeds/        # Categorías, admin user
├── frontend/         # React dashboard (next phase)
├── docker/           # Container config (for dev)
├── tests/            # Unit + Integration
└── docs/             # Architecture docs
```

## Requisitos

- Python 3.11+
- PostgreSQL 15+ (con pgvector)
- Cuenta en Cloudinary (gratis)
- Token de BotFather para Telegram
- Cuenta en Neon (PostgreSQL serverless gratis)
- (Opcional) Cuenta en Render para deploy

## Configuración Rápida

```bash
# 1. Clonar e instalar
git clone <repo> && cd botnoticias
cp .env.example .env

# 2. Editar .env con tus credenciales
#    TELEGRAM_BOT_TOKEN, DATABASE_URL, CLOUDINARY_*, HF_API_TOKEN

# 3. Instalar dependencias
make install

# 4. Inicializar DB
make db-init

# 5. Iniciar servidor de desarrollo
make dev
```

## Deploy en Render (1-click)

1. Conecta tu repo a Render
2. Render detectará `render.yaml` automáticamente
3. Configura las variables de entorno secretas en Render Dashboard
4. El cron job `keep-alive` evitará el sleep del free tier

## Variables de Entorno

| Variable | Descripción |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Token de @BotFather |
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `HF_API_TOKEN` | Hugging Face API token |
| `SECRET_KEY` | JWT secret (generar con `openssl rand -hex 32`) |
| `ADMIN_EMAIL` | Email del admin inicial |
| `ADMIN_PASSWORD` | Password del admin inicial |

## Comandos Útiles

```bash
make install      # Instalar dependencias
make dev          # Servidor desarrollo (uvicorn reload)
make lint         # Ruff + mypy
make format       # Ruff format
make test         # Pytest con coverage
make db-init      # Crear tablas + seeds
```

## API Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/register` | Registrar usuario |
| GET | `/api/v1/auth/me` | Perfil actual |
| GET/POST | `/api/v1/sources/` | CRUD fuentes |
| GET/POST | `/api/v1/categories/` | CRUD categorías |
| GET | `/api/v1/news/` | Listar noticias |
| GET | `/api/v1/news/approval-queue` | Cola de aprobación |
| POST | `/api/v1/news/{id}/approve` | Aprobar/rechazar |
| GET | `/health` | Health check |

## Licencia

MIT
