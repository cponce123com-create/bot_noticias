FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

# Copy app code
COPY backend/ backend/
COPY workers/ workers/
COPY ai/ ai/
COPY database/ database/
COPY config/ config/
COPY scripts/ scripts/

# Create media dirs
RUN mkdir -p media/images media/videos

# Create non-root user
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Start with uvicorn
# NOTA: --workers 1 es intencional. El APScheduler corre dentro del proceso web.
# Si se aumenta workers, los jobs del scheduler se duplicarian.
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --workers 1
