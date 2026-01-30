FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY packages /app/packages
COPY apps/worker_ingest /app/apps/worker_ingest
COPY .env.example /app/.env

# Start worker
CMD python -m apps.worker_ingest.main
