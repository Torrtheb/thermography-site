#!/bin/bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput
echo "=== Migrations complete ==="

echo "=== Creating cache table (if needed) ==="
python manage.py createcachetable --database default 2>/dev/null || true
echo "=== Cache table ready ==="

echo "=== Starting gunicorn on port ${PORT:-8000} ==="
# Gunicorn flags chosen for Railway + Neon (free tier) realities:
#   --timeout 30           Railway's edge proxy gives up at ~15s, so longer here
#                          just keeps workers tied up on requests the client never
#                          saw. 30s leaves headroom for a Neon cold start while
#                          still recycling fast.
#   --graceful-timeout 30  let in-flight requests finish on rolling restart.
#   --worker-tmp-dir /dev/shm  Gunicorn's heartbeat file on a tmpfs avoids
#                          stalls when the container disk is slow.
#   (no --preload)         preload shares one DB connection state across the
#                          fork; a single Neon cold-start failure during preload
#                          poisons every worker. Without preload each worker
#                          recovers independently.
exec gunicorn thermography_site.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --threads 4 \
    --timeout 30 \
    --graceful-timeout 30 \
    --worker-tmp-dir /dev/shm \
    --log-level info \
    --access-logfile - \
    --error-logfile -
