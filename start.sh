#!/bin/bash
# Quick start script for AI Knowledge Bench

set -e

echo "🤖 AI Knowledge Bench - Quick Start"
echo "===================================="
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env from .env.example..."
    cp .env.example .env
    echo "✅ .env created. You can edit it to customize settings."
    echo ""
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

echo "🐳 Starting services with Docker Compose..."
cd deploy

# Start services
if ! docker compose --env-file ../.env up -d; then
    echo ""
    echo "⚠️  docker compose up failed. This host may restrict stopping/recreating containers (permission denied)."
    echo "    Retrying without recreating existing containers..."
    docker compose --env-file ../.env up -d --no-recreate
fi

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
docker compose ps

echo ""
echo "✅ Services started successfully!"
echo ""
echo "📍 Access points:"
echo "   - Web UI: http://localhost:8080"
echo "   - API Docs: http://localhost:8080/docs"
echo "   - PostgreSQL: localhost:5432"
echo "   - Kafka: localhost:9092"
echo "   - Redis: localhost:6379"
echo ""
echo "📊 View logs:"
echo "   docker compose logs -f web_api"
echo "   docker compose logs -f worker_ingest"
echo ""
echo "🛑 Stop services:"
echo "   cd deploy && docker compose down"
echo ""
echo "📚 Next steps:"
echo "   1. Set up vLLM (see README.md)"
echo "   2. Upload a document at http://localhost:8080"
echo "   3. Ask questions in the chat interface"
echo ""
echo "For more information, see README.md"
