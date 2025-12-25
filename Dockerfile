# Multi-stage Dockerfile for CarbonLens
FROM python:3.11-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OWID_DATA_PATH=/app/data/owid-co2-data.csv

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Create data directory and download OWID data during build
RUN mkdir -p /app/data && \
    curl -L -o /app/data/owid-co2-data.csv \
    https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv

# Copy project
COPY . /app

# Make entrypoint executable and create a non-root user
RUN chmod +x /app/entrypoint.sh && \
    addgroup --system app && adduser --system --ingroup app app && \
    chown -R app:app /app/data

# Expose the Django port
EXPOSE 8000

# Use an entrypoint to run migrations/collectstatic then start Gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command runs Gunicorn for production using the Python module
ENV GUNICORN_WORKERS=1
ENV GUNICORN_TIMEOUT=120

# Run gunicorn via python module; allow overriding workers and timeout via env vars
CMD ["sh", "-c", "python -m gunicorn carbonlens.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS} --timeout ${GUNICORN_TIMEOUT}"]