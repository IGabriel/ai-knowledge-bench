# System Dependencies Guide

This document details all system dependencies required for AI Knowledge Bench beyond Python libraries.

## Overview

AI Knowledge Bench requires several external components to function properly. These can be installed natively on your system or run via Docker (recommended).

## Required System Dependencies

### 1. Docker & Docker Compose

**Required for**: Container orchestration and running all services

**Versions**:
- Docker: 20.10+ (recommended: 24.0+)
- Docker Compose: 2.0+ (v2 syntax)

**Installation**:

**Ubuntu/Debian**:
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Verify installation
docker --version
docker compose version
```

**macOS**:
```bash
# Install Docker Desktop
brew install --cask docker

# Or download from: https://www.docker.com/products/docker-desktop
```

**Windows**:
- Download and install Docker Desktop from https://www.docker.com/products/docker-desktop
- Enable WSL 2 backend for better performance

**Why needed**: Docker Compose orchestrates all services (PostgreSQL, Kafka, Redis, Web API, Worker) as containers, simplifying setup and ensuring consistent environments.

---

### 2. PostgreSQL with pgvector Extension

**Required for**: Vector database for embeddings and document storage

**Version**: PostgreSQL 15+ with pgvector 0.5.0+

**Docker Setup** (Recommended):
```yaml
# Already configured in deploy/docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: bench_user
      POSTGRES_PASSWORD: bench_pass
      POSTGRES_DB: ai_knowledge_bench
    ports:
      - "5432:5432"
```

**Native Installation** (Ubuntu/Debian):
```bash
# Install PostgreSQL
sudo apt-get update
sudo apt-get install -y postgresql-15 postgresql-server-dev-15

# Install pgvector
cd /tmp
git clone --branch v0.5.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# Enable extension
sudo -u postgres psql -d ai_knowledge_bench -c "CREATE EXTENSION vector;"
```

**macOS**:
```bash
# Install PostgreSQL
brew install postgresql@15

# Install pgvector
brew install pgvector

# Start PostgreSQL
brew services start postgresql@15
```

**Why needed**: Stores document metadata, chunks, and vector embeddings for similarity search. The pgvector extension enables efficient nearest-neighbor search on embeddings.

---

### 3. Apache Kafka

**Required for**: Message queue for asynchronous document ingestion

**Version**: 3.5+ (using KRaft mode, no Zookeeper required)

**Docker Setup** (Recommended):
```yaml
# Already configured in deploy/docker-compose.yml
services:
  kafka:
    image: apache/kafka:3.7.0
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    ports:
      - "9092:9092"
```

**Native Installation** (Ubuntu/Debian):
```bash
# Download Kafka
cd /tmp
wget https://downloads.apache.org/kafka/3.7.0/kafka_2.13-3.7.0.tgz
tar -xzf kafka_2.13-3.7.0.tgz
sudo mv kafka_2.13-3.7.0 /opt/kafka

# Configure KRaft mode
cd /opt/kafka
KAFKA_CLUSTER_ID="$(bin/kafka-storage.sh random-uuid)"
bin/kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c config/kraft/server.properties

# Start Kafka
bin/kafka-server-start.sh config/kraft/server.properties
```

**macOS**:
```bash
# Install via Homebrew
brew install kafka

# Start Kafka
brew services start kafka
```

**Why needed**: Kafka handles asynchronous document processing. When documents are uploaded, events are sent to Kafka topics, and worker processes consume these events to perform extraction, chunking, and embedding.

---

### 4. Redis

**Required for**: Caching and session management

**Version**: 6.0+ (recommended: 7.0+)

**Docker Setup** (Recommended):
```yaml
# Already configured in deploy/docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

**Native Installation** (Ubuntu/Debian):
```bash
# Install Redis
sudo apt-get update
sudo apt-get install -y redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify
redis-cli ping
```

**macOS**:
```bash
# Install via Homebrew
brew install redis

# Start Redis
brew services start redis
```

**Why needed**: Redis is used for caching embedding results, storing temporary session data, and coordinating distributed workers.

---

### 5. vLLM (Optional but Recommended)

**Required for**: LLM inference for generating answers

**Version**: 0.2.0+

**Installation**:
```bash
# Install vLLM
pip install vllm

# Run vLLM server (CPU mode)
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --dtype auto \
  --device cpu \
  --max-model-len 2048 \
  --port 8000

# Or use GPU if available
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --dtype auto \
  --device cuda \
  --max-model-len 4096 \
  --port 8000
```

**System Requirements**:
- **CPU mode**: 8GB+ RAM, modern CPU
- **GPU mode**: NVIDIA GPU with 8GB+ VRAM, CUDA 11.8+

**Alternative Models**:
- Small: `Qwen/Qwen2.5-0.5B-Instruct` (~500MB)
- Medium: `Qwen/Qwen2.5-1.5B-Instruct` (~1.5GB)
- Large: `Qwen/Qwen2.5-3B-Instruct` (~3GB)

**Why needed**: vLLM provides the language model for generating natural language answers based on retrieved document chunks. It exposes an OpenAI-compatible API.

---

## Optional Dependencies

### Python 3.11+

If running components outside Docker:

**Installation** (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
```

**macOS**:
```bash
brew install python@3.11
```

### Build Tools

For compiling certain Python packages:

**Ubuntu/Debian**:
```bash
sudo apt-get install -y build-essential libpq-dev
```

**macOS**:
```bash
xcode-select --install
```

---

## Deployment Options

### Option 1: Docker Compose (Recommended)

All dependencies run in containers:

```bash
cd deploy
docker compose up -d
```

**Pros**:
- Easy setup, no manual dependency installation
- Consistent environment
- Easy cleanup

**Cons**:
- Requires Docker
- Higher resource usage

### Option 2: Hybrid (vLLM Separate)

Run PostgreSQL, Kafka, Redis in Docker; vLLM separately:

```bash
# Start core services
cd deploy
docker compose up -d postgres kafka redis web_api worker_ingest

# Run vLLM separately
pip install vllm
vllm serve Qwen/Qwen2.5-0.5B-Instruct --device cpu --port 8000
```

**Pros**:
- Flexibility to run vLLM on different hardware
- Easier to debug vLLM issues

**Cons**:
- More complex setup

### Option 3: Native Installation

Install all dependencies natively:

**Pros**:
- Maximum performance
- Fine-grained control

**Cons**:
- Complex setup
- Environment-specific issues
- Harder to replicate

---

## Minimum System Requirements

### For Development (Docker Compose):
- **CPU**: 4 cores
- **RAM**: 8GB minimum, 16GB recommended
- **Disk**: 20GB free space
- **OS**: Linux, macOS, Windows 10+ with WSL 2

### For Production:
- **CPU**: 8+ cores
- **RAM**: 32GB minimum, 64GB recommended
- **Disk**: 100GB+ SSD
- **GPU**: NVIDIA GPU with 16GB+ VRAM (for vLLM)
- **Network**: 1Gbps+ for distributed setups

---

## Verification

Check all dependencies are working:

```bash
# Validate setup
bash validate.sh

# Check Docker services
cd deploy
docker compose ps

# Test individual services
docker compose exec postgres psql -U bench_user -d ai_knowledge_bench -c "SELECT version();"
docker compose exec kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092
docker compose exec redis redis-cli ping

# Test vLLM
curl http://localhost:8000/v1/models

# Test Web API
curl http://localhost:8080/health
```

---

## Troubleshooting

### Docker Issues

**"Cannot connect to Docker daemon"**:
```bash
# Start Docker
sudo systemctl start docker  # Linux
# or restart Docker Desktop on macOS/Windows
```

**"Port already in use"**:
```bash
# Find and kill process using port
sudo lsof -i :5432  # or :9092, :6379, :8080
sudo kill -9 <PID>
```

### PostgreSQL Issues

**"pgvector extension not found"**:
```bash
# Rebuild with correct image
cd deploy
docker compose down
docker compose up -d postgres
```

### Kafka Issues

**"Connection refused to Kafka"**:
```bash
# Check Kafka is running
docker compose logs kafka

# Recreate Kafka
docker compose rm -sf kafka
docker compose up -d kafka
```

### vLLM Issues

**"Out of memory"**:
```bash
# Use smaller model
vllm serve Qwen/Qwen2.5-0.5B-Instruct --device cpu --max-model-len 1024

# Or reduce context length
vllm serve Qwen/Qwen2.5-1.5B-Instruct --device cpu --max-model-len 2048
```

---

## Summary

| Component | Required | Version | Purpose |
|-----------|----------|---------|---------|
| Docker | Yes | 20.10+ | Container orchestration |
| Docker Compose | Yes | 2.0+ | Service orchestration |
| PostgreSQL | Yes | 15+ | Document & metadata storage |
| pgvector | Yes | 0.5.0+ | Vector similarity search |
| Kafka | Yes | 3.5+ | Asynchronous processing |
| Redis | Yes | 6.0+ | Caching & sessions |
| vLLM | Recommended | 0.2.0+ | LLM inference |
| Python | Optional* | 3.11+ | Local development |

\* Required only for local development outside Docker

---

For more information, see:
- [README.md](README.md) - Full project documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick setup guide
- [docs/design.md](docs/design.md) - Architecture details
