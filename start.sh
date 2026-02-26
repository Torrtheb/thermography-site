#!/bin/bash
set -e

echo "=== [1/3] Starting migrations ==="
python manage.py migrate --noinput 2>&1
echo "=== [2/3] Migrations complete ==="

echo "=== [3/3] Starting gunicorn on port ${PORT:-8000} ==="
echo "DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE"
echo "ALLOWED_HOSTS=$ALLOWED_HOSTS"

exec gunicorn thermography_site.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --preload \
    --log-level debug \
    --access-logfile - \
    --error-logfile - \
    2>&1
