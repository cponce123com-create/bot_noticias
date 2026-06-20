# TASKS.md - Auditoria y Optimizacion de Noticiando.pe

## Fase 1: Seguridad (Completado)
- [x] `.env.render` eliminado del repositorio
- [x] `.gitignore` actualizado con `.env.render`
- [x] `config.py`: SECRET_KEY y ADMIN_PASSWORD sin defaults (forzados desde entorno)
- [x] CORS dinamico desde `ALLOWED_ORIGINS`
- [x] `ENABLE_SCHEDULER` para controlar scheduler por entorno

## Fase 2: Scheduler (Completado)
- [x] Funcion `get_scheduler()` con `SQLAlchemyJobStore` para persistencia en PostgreSQL
- [x] Scheduler controlado por `ENABLE_SCHEDULER` (desactivar en web service)

## Fase 3: Resiliencia (Completado)
- [x] Backoff exponencial en scraping HTTP (max 3 intentos, espera 2^n segundos)
- [x] Rate limiting con slowapi (30 req/min default)

## Fase 4: Docker (Completado)
- [x] Dockerfile multi-stage (builder + runtime)
- [x] Dependencias AI opcionales (`pip install .[ai]`)
- [x] `httpx` duplicado eliminado de pyproject.toml
- [x] Nuevas dependencias: `tenacity`, `slowapi`, `psutil`
- [x] FastAPI compatible con version 0.115+

## Fase 5: Logs (Completado)
- [x] `exc_info=True` agregado en bloques except clave
- [x] Este archivo `TASKS.md`

## Auditoria de Seguridad - Pendientes

- [ ] Rotar SECRET_KEY en produccion (actualmente en env de Render)
- [ ] Rotar ADMIN_PASSWORD en produccion
- [ ] Verificar que TELEGRAM_BOT_TOKEN este solo como `sync: false` en Render (ya no hardcodeado)
- [ ] Verificar que CLOUDINARY_* credenciales esten solo como `sync: false` (ya no hardcodeadas en codigo)
- [ ] Agregar rate limiting por IP en login endpoint
- [ ] Implementar refresh tokens para sesiones JWT de larga duracion
- [ ] Auditoria de logs de acceso (quien aprueba/rechaza noticias)
- [ ] Migrar a variables de entorno en Render dashboard para TELEGRAM_ADMIN_ID (ya no hardcodeado)

## Variables de Entorno NUEVAS en Render:

| Variable | Descripcion | Default | Obligatoria |
|---|---|---|---|
| `SECRET_KEY` | Clave secreta para JWT (generar con `openssl rand -hex 32`) | — | **SI** |
| `ADMIN_PASSWORD` | Password del admin por defecto | — | **SI** |
| `ALLOWED_ORIGINS` | Origenes CORS separados por coma | `http://localhost:5173,http://localhost:3000` | No |
| `ENABLE_SCHEDULER` | Activar scheduler interno en el web service | `true` | No |

## Pasos post-deploy

1. **Render → Environment Variables**:
   - `SECRET_KEY` = valor generado con `openssl rand -hex 32`
   - `ADMIN_PASSWORD` = nueva password segura
   - `ALLOWED_ORIGINS` = `https://bot-noticias-static.onrender.com`
   - `ENABLE_SCHEDULER` = `true` (o `false` si usas cron separado)

2. **Hacer deploy manual** del backend
3. **Verificar** que el health endpoint responda: `https://bot-noticias-dx2d.onrender.com/health`
4. **Verificar** que `/metrics` funcione: `https://bot-noticias-dx2d.onrender.com/metrics`
