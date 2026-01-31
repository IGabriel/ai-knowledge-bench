FROM python:3.11-slim

WORKDIR /app

ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# Install system dependencies
RUN set -eux; \
        if [ -f /etc/apt/sources.list ]; then \
            sed -i "s|http://deb.debian.org/debian|https://${APT_MIRROR}/debian|g" /etc/apt/sources.list; \
            sed -i "s|http://security.debian.org/debian-security|https://${APT_MIRROR}/debian-security|g" /etc/apt/sources.list; \
        fi; \
        if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
            sed -i "s|http://deb.debian.org/debian|https://${APT_MIRROR}/debian|g" /etc/apt/sources.list.d/debian.sources; \
            sed -i "s|http://security.debian.org/debian-security|https://${APT_MIRROR}/debian-security|g" /etc/apt/sources.list.d/debian.sources; \
        fi; \
        apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN python -m pip config set global.index-url "$PIP_INDEX_URL" \
    && python -m pip config set global.trusted-host "$PIP_TRUSTED_HOST" \
    && python -m pip install --no-cache-dir -U pip \
    && python -m pip install --no-cache-dir -r requirements.txt

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
