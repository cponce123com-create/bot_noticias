#!/bin/bash
# scripts/start.sh - Production startup for Render
set -e

echo "=== Noticiando.pe - Production Start ==="

# Print Python version
python3 --version

# Run DB migrations (if needed) - using synchronous connection
echo "Checking database connection..."
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect('${DATABASE_URL_SYNC}')
    print('DB connection OK')
    conn.close()
except Exception as e:
    print(f'DB connection error: {e}')
    exit(1)
"

# Start uvicorn
echo "Starting FastAPI server..."
exec uvicorn backend.app.main:app 
    --host 0.0.0.0 
    --port ${PORT:-8000} 
    --workers 1 
    --log-level info 
    --no-access-log
