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
COPY apps/web_api /app/apps/web_api
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY .env.example /app/.env

# Create upload directory
RUN mkdir -p /app/data/uploads /app/reports

# Expose port
EXPOSE 8080

# Run migrations and start app
CMD alembic upgrade head && python -m apps.web_api.main
