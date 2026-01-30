# Quick Start Guide

This is a streamlined guide to get you up and running with AI Knowledge Bench quickly.

## Prerequisites

- Docker & Docker Compose installed
- 8GB+ RAM
- (Optional) GPU for better performance

## 5-Minute Setup

### 1. Clone and Validate

```bash
git clone https://github.com/IGabriel/ai-knowledge-bench.git
cd ai-knowledge-bench

# Validate setup
bash validate.sh
```

### 2. Start Services

```bash
# Option A: Using the start script
./start.sh

# Option B: Using Make
make dev

# Option C: Manual Docker Compose
cd deploy
docker compose up -d
```

Wait ~30 seconds for services to initialize.

### 3. Set Up vLLM (CPU Mode)

In a separate terminal:

```bash
# Install vLLM
pip install vllm

# Run vLLM server (CPU mode)
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --dtype auto \
  --device cpu \
  --max-model-len 2048 \
  --port 8000
```

**Note**: CPU inference is slow (~5-20 tokens/sec). For production, use GPU.

### 4. Access the UI

Open your browser to: **http://localhost:8080**

## First Steps

### Upload a Document

1. Click "Choose File" in the upload section
2. Select a PDF, DOCX, PPTX, XLSX, HTML, MD, or TXT file
3. Click "Upload"
4. Wait for ingestion (check logs: `docker compose logs -f worker_ingest`)

### Ask Questions

1. Type your question in the chat input
2. Press Enter or click "Send"
3. Watch the streaming response
4. See citations below the answer

## Useful Commands

```bash
# View logs
make logs              # All services
make logs-api          # Web API only
make logs-worker       # Worker only

# Service management
make stop              # Stop services
make restart           # Restart services
make ps                # Service status

# Database
make shell-db          # PostgreSQL shell
make upgrade           # Run migrations

# Development
make format            # Format code
make lint              # Lint code
```

## Troubleshooting

### Services not starting

```bash
# Check Docker
docker ps
docker compose ps

# View specific service logs
docker compose logs postgres
docker compose logs kafka
```

### vLLM connection errors

1. Ensure vLLM is running on port 8000
2. Check vLLM logs for errors
3. Test endpoint: `curl http://localhost:8000/v1/models`

### Worker not processing documents

```bash
# Check worker logs
docker compose logs -f worker_ingest

# Check Kafka
docker compose exec kafka kafka-topics.sh \
  --list --bootstrap-server localhost:9092
```

### Database connection issues

```bash
# Restart PostgreSQL
docker compose restart postgres

# Check database
docker compose exec postgres psql -U bench_user -d ai_knowledge_bench
```

## Next Steps

1. **Read the full documentation**: See [README.md](README.md)
2. **Experiment with chunk profiles**: Create and test different chunking strategies
3. **Run evaluations**: Use the golden set to measure quality
4. **Deploy to production**: See [docs/design.md](docs/design.md) for scaling considerations

## Architecture Overview

```
User → FastAPI (Web UI + API)
          ↓
    PostgreSQL + pgvector (Vector DB)
          ↓
    Retrieval → vLLM (Generation)
          ↑
    Worker ← Kafka (Events)
```

## Key Concepts

- **Chunk Profiles**: Experiment with different chunk sizes (512, 1024, etc.)
- **Source Refs**: Precise citations (page=5, slide=3, sheet=Sales)
- **Strict Matching**: Evaluation requires exact document+source match
- **Embeddings**: multilingual-e5-small by default (384 dimensions)

## Configuration

Edit `.env` to customize:

- `EMBEDDING_MODEL`: Change embedding model
- `VLLM_MODEL`: Change LLM model
- `DEFAULT_CHUNK_SIZE`: Default chunking size
- `DEFAULT_TOP_K`: Number of retrieved chunks

## Support

- **Issues**: Open an issue on GitHub
- **Documentation**: See [README.md](README.md) and [docs/design.md](docs/design.md)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md)

## Performance Notes

**Current setup (CPU mode)**:
- Embedding: ~100-500 chunks/minute
- Vector search: ~10-50ms per query
- LLM inference: ~5-20 tokens/second

**For production (GPU)**:
- Embedding: ~5000+ chunks/minute
- Vector search: ~5-10ms per query
- LLM inference: ~100-500 tokens/second

Happy building! 🚀
