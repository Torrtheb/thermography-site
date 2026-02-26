#!/bin/bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput
echo "=== Migrations complete ==="

echo "=== Starting gunicorn on port ${PORT:-8000} ==="
exec gunicorn thermography_site.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --preload \
    --log-level info \
    --access-logfile - \
    --error-logfile -
