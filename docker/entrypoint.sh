#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed_demo
python manage.py collectstatic --noinput

exec gunicorn config.wsgi \
  --bind 0.0.0.0:8000 \
  --timeout 180 \
  --workers "${GUNICORN_WORKERS:-3}"
