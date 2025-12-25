#!/bin/sh
set -e

# Entrypoint for container: run migrations, collect static, then exec passed command

echo "Running database migrations (if DB available)..."
python manage.py migrate --noinput || echo "Migrations failed or DB unavailable; continuing"

echo "Collecting static files..."
python manage.py collectstatic --noinput || echo "collectstatic failed or storage unavailable; continuing"

# Ensure OWID data is present; download if missing
DATA_PATH="${DATABASE_PATH:-/app/data/owid-co2-data.csv}"
if [ ! -f "$DATA_PATH" ]; then
	echo "OWID data not found at $DATA_PATH. Attempting to download..."
	# Try to run the included download script
	if python /app/scripts/download_owid_data.py; then
		echo "OWID data downloaded successfully"
	else
		echo "Failed to download OWID data. The API will start but dataset-dependent endpoints may fail." >&2
	fi
else
	echo "OWID data found at $DATA_PATH"
fi

exec "$@"
