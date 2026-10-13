#!/bin/sh
set -eu
export DJANGO_DB_CONN_MAX_AGE=0
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec python -m uvicorn backend.asgi:application --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --loop uvloop --http httptools --lifespan off --no-proxy-headers --ws-max-size 16384 --limit-concurrency "${WEB_LIMIT_CONCURRENCY:-32}" --timeout-keep-alive 5 --timeout-graceful-shutdown 90
