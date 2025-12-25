# Multi-stage Dockerfile for CarbonLens
FROM python:3.11-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

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

# Copy project
COPY . /app

# Make entrypoint executable and create a non-root user
RUN chmod +x /app/entrypoint.sh || true && \
    addgroup --system app && adduser --system --ingroup app app || true

# Expose the Django port
EXPOSE 8000

# Use an entrypoint to run migrations/collectstatic then start Gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command runs Gunicorn for production using the Python module
# Use `python -m gunicorn` to avoid relying on PATH when the gunicorn
# executable isn't found at runtime in some environments.
CMD ["python", "-m", "gunicorn", "carbonlens.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]

