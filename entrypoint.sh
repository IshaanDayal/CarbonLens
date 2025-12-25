#!/bin/sh
set -e

# Entrypoint for container: run migrations, collect static, then exec passed command

echo "Running database migrations (if DB available)..."
python manage.py migrate --noinput || echo "Migrations failed or DB unavailable; continuing"

echo "Collecting static files..."
python manage.py collectstatic --noinput || echo "collectstatic failed or storage unavailable; continuing"

exec "$@"
