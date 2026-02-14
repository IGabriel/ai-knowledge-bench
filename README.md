# AI Knowledge Bench 🤖

An end-to-end **RAG (Retrieval-Augmented Generation) knowledge assistant** with built-in evaluation harness to iterate on chunking and retrieval quality.

## Features ✨

- **FastAPI Web App** with simple HTML/JS UI for document upload and chat
- **SSE Streaming** chat endpoint for real-time responses
- **Kafka-based** ingestion pipeline for scalable document processing
- **PostgreSQL + pgvector** for efficient vector similarity search
- **Configurable embedding models** (default: `intfloat/multilingual-e5-small`)
- **Local inference via vLLM** with CPU support (configurable model)
- **Dynamic chunking strategies** with profile management
- **Evaluation harness** with Golden Set (50 items) and comprehensive metrics
- **Docker Compose** setup for easy local development

## Architecture 🏗️

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                           │
│                    (Browser / FastAPI UI)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FastAPI Web API                            │
│  • Document Upload • Chat (SSE Stream) • Chunk Profiles         │
│  • Reindex Trigger • Health Check                               │
└──────┬────────────────────────────────────┬─────────────────────┘
       │                                    │
       │ Kafka Events                       │ Query
       │                                    │
       ▼                                    ▼
┌─────────────────┐              ┌──────────────────────┐
│  Kafka Topics   │              │   PostgreSQL         │
│  • ingest       │              │   + pgvector         │
│  • reindex      │              │   • Documents        │
└────────┬────────┘              │   • Chunks           │
         │                       │   • Embeddings       │
         │                       │   • Profiles         │
         ▼                       └──────────┬───────────┘
┌─────────────────┐                         │
│ Ingestion       │                         │ Vector Search
│ Worker          │◄────────────────────────┘
│ • Load Docs     │
│ • Extract       │              ┌──────────────────────┐
│ • Chunk         │              │   vLLM (OpenAI API)  │
│ • Embed         │              │   • Qwen2.5-0.5B     │
└─────────────────┘              │   • CPU Inference    │
                                 │   • Streaming        │
                                 └──────────────────────┘
```

## Quick Start 🚀

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- 8GB+ RAM recommended
- For vLLM: additional compute resources (can run separately)

📖 **For detailed system dependencies**, see:
- [DEPENDENCIES.md](DEPENDENCIES.md) - Complete system dependencies guide (English)
- [DEPENDENCIES_zh.md](DEPENDENCIES_zh.md) - 系统依赖完整指南（中文）

### 1. Clone and Setup

```bash
git clone https://github.com/IGabriel/ai-knowledge-bench.git
cd ai-knowledge-bench

# Copy environment file
cp .env.example .env

# Optional: Adjust settings in .env
```

### 2. Start the Stack

```bash
cd deploy
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f web_api
docker compose logs -f worker_ingest
```

Services will be available at:
- **Web UI**: http://localhost:8080
- **API Docs**: http://localhost:8080/docs
- **PostgreSQL**: localhost:5432
- **Kafka**: localhost:9092
- **Redis**: localhost:6379

### 3. vLLM Setup (Optional)

The vLLM service is commented out in `docker-compose.yml` as it can be resource-intensive. You have two options:

**Option A: Run vLLM in Docker** (uncomment in docker-compose.yml)

**Option B: Run vLLM Separately** (Recommended for development)

```bash
# Install vLLM
pip install vllm

# Run vLLM server with CPU
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --dtype auto \
  --device cpu \
  --max-model-len 2048 \
  --port 8000

# Or use a slightly larger model if you have resources
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --dtype auto \
  --device cpu \
  --max-model-len 2048 \
  --port 8000
```

Update `.env` with vLLM URL:
```
VLLM_BASE_URL=http://localhost:8000/v1
```

### 4. Initialize Database

The database will be automatically initialized with migrations when the web_api container starts. To run migrations manually:

```bash
# Inside web_api container
docker compose exec web_api alembic upgrade head

# Or locally
pip install -r requirements.txt
alembic upgrade head
```

### 5. Upload Documents and Chat

**Via Web UI:**
1. Open http://localhost:8080
2. Upload a document (PDF, DOCX, PPTX, XLSX, HTML, MD, TXT)
3. Wait for ingestion (check worker logs: `docker compose logs -f worker_ingest`)
4. Ask questions in the chat interface

**Via API:**
```bash
# Upload document
curl -X POST "http://localhost:8080/v1/documents" \
  -F "file=@/path/to/document.pdf"

# List documents
curl "http://localhost:8080/v1/documents"

# Chat (SSE stream)
curl -N "http://localhost:8080/v1/chat/stream?query=What%20is%20this%20document%20about?"
```

## Chunk Profiles 📊

Chunk profiles allow you to experiment with different chunking strategies:

```bash
# List profiles
curl "http://localhost:8080/v1/chunk-profiles"

# Create new profile
curl -X POST "http://localhost:8080/v1/chunk-profiles" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "large-chunks",
    "description": "Larger chunks for broader context",
    "chunk_size": 1024,
    "chunk_overlap": 256
  }'

# Activate profile
curl -X POST "http://localhost:8080/v1/chunk-profiles/{profile_id}/activate"

# Reindex documents with new profile
curl -X POST "http://localhost:8080/v1/reindex" \
  -H "Content-Type: application/json" \
  -d '{
    "chunk_profile_id": "{profile_id}"
  }'
```

## Evaluation Harness 📈

Run evaluations to measure RAG system quality:

```bash
# Get active chunk profile ID first
PROFILE_ID=$(curl -s "http://localhost:8080/v1/chunk-profiles" | jq -r '.[] | select(.is_active==true) | .id')

# Run evaluation
docker compose exec web_api python -m packages.eval.run \
  --dataset eval/golden_set_v1.jsonl \
  --profile "$PROFILE_ID" \
  --topk 5 \
  --embedding intfloat/multilingual-e5-small \
  --llm Qwen/Qwen2.5-0.5B-Instruct

# Or locally (with all dependencies installed)
python -m packages.eval.run \
  --dataset eval/golden_set_v1.jsonl \
  --profile YOUR_PROFILE_ID \
  --topk 5
```

### Metrics Explained

The evaluation harness computes:

1. **Embedding Coverage**: Ratio of retrieved chunks (should be ≥ 0.99)
2. **Recall@K**: Fraction of expected sources found in top-K results (strict match)
3. **MRR (Mean Reciprocal Rank)**: Position of first correct result
4. **Semantic Similarity**: Cosine similarity between expected and generated answers
5. **Semantic Correct Rate**: % of answers above similarity threshold
6. **Citation Hit Rate**: % of questions with at least one correct source cited
7. **Composite Score**: Weighted combination (30% recall, 20% MRR, 30% semantic, 20% citation)

### Golden Set Format

The golden set (`eval/golden_set_v1.jsonl`) contains 50 test questions:
- 25 from PDFs
- 10 from PPTX
- 5 from XLSX
- 5 from DOCX
- 5 from MD/HTML/TXT

Before running evaluation, **replace UUID placeholders** with actual document IDs from your uploaded documents.

## Development 💻

### Local Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install -e ".[dev]"

# Run linters
black .
ruff check .

# Run tests (if implemented)
pytest
```

### Project Structure

```
ai-knowledge-bench/
├── apps/
│   ├── web_api/          # FastAPI application
│   └── worker_ingest/    # Kafka consumer for ingestion
├── packages/
│   ├── core/             # Shared core functionality
│   │   ├── config.py     # Configuration management
│   │   ├── database.py   # SQLAlchemy models
│   │   ├── loaders.py    # Document loaders
│   │   ├── chunking.py   # Chunking strategies
│   │   ├── embeddings.py # Embedding generation
│   │   ├── retrieval.py  # Vector search & retrieval
│   │   ├── vllm_client.py# vLLM client wrapper
│   │   └── kafka_utils.py# Kafka utilities
│   └── eval/             # Evaluation harness
├── deploy/
│   ├── docker-compose.yml
│   └── init-db.sh
├── docs/                 # Documentation
├── eval/                 # Golden set and test data
├── alembic/             # Database migrations
└── data/                # Runtime data (uploads, etc.)
```

## Configuration ⚙️

Key environment variables (see `.env.example`):

```bash
# Database
DATABASE_URL=postgresql://bench_user:bench_pass@localhost:5432/ai_knowledge_bench

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC_INGEST=document.ingest.requested
KAFKA_TOPIC_REINDEX=document.reindex.requested

# Embeddings
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIMENSION=384
EMBEDDING_DEVICE=cpu

# vLLM
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=Qwen/Qwen2.5-0.5B-Instruct

# Chunking
DEFAULT_CHUNK_SIZE=512
DEFAULT_CHUNK_OVERLAP=128

# Retrieval
DEFAULT_TOP_K=5
DEFAULT_SIMILARITY_THRESHOLD=0.7
```

## Supported Document Formats 📄

- **PDF** (.pdf) - Page-based sections
- **Word** (.docx) - Heading-based sections
- **PowerPoint** (.pptx) - Slide-based sections
- **Excel** (.xlsx, .xls) - Sheet-based sections
- **HTML** (.html, .htm) - Heading-based sections
- **Markdown** (.md) - Heading-based sections
- **Text** (.txt) - Single section

## Troubleshooting 🔧

### Common Issues

**1. vLLM connection errors**
- Ensure vLLM is running and accessible at `VLLM_BASE_URL`
- Check vLLM logs for model loading issues
- For CPU inference, expect slower performance

**2. Kafka connection issues**
```bash
# Check Kafka health
docker compose exec kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

**3. Database migration errors**
```bash
# Reset database (WARNING: deletes all data)
docker compose down -v
docker compose up -d postgres
docker compose exec web_api alembic upgrade head
```

**4. Worker not processing documents**
```bash
# Check worker logs
docker compose logs -f worker_ingest

# Check Kafka topics
docker compose exec kafka kafka-topics.sh --list --bootstrap-server localhost:9092

# Check messages in topic
docker compose exec kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic document.ingest.requested \
  --from-beginning
```

**5. Out of memory errors**
- Reduce `EMBEDDING_BATCH_SIZE` in `.env`
- Use a smaller vLLM model
- Increase Docker memory limits

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f web_api
docker compose logs -f worker_ingest

# Database logs
docker compose logs -f postgres
```

## Design Notes 📝

See [docs/design.md](docs/design.md) for detailed information about:
- Chunk profile system
- Embedding strategy (separate tables per model)
- Strict source_ref matching rules
- Retrieval and ranking

## Performance Considerations ⚡

- **Embedding Generation**: CPU-based, ~100-500 chunks/minute (varies by hardware)
- **Vector Search**: ivfflat index, ~10-50ms query time for 10K documents
- **vLLM Inference**: CPU mode, ~5-20 tokens/second (depends on model size)
- **Scalability**: Target ~10K documents, ~300 pages each, ~3M chunks

For production deployments:
- Use GPU for embeddings and inference
- Switch to HNSW index for better query performance
- Add load balancing for web_api
- Scale worker_ingest horizontally
- Use managed Kafka (e.g., Confluent Cloud, AWS MSK)

## Contributing 🤝

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests (if applicable)
5. Run linters: `black . && ruff check .`
6. Submit a pull request

## Documentation 📚

- [README.md](README.md) - This file, main project documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide for getting up and running fast
- [DEPENDENCIES.md](DEPENDENCIES.md) - Complete system dependencies guide (English)
- [DEPENDENCIES_zh.md](DEPENDENCIES_zh.md) - 系统依赖完整指南（中文）
- [docs/design.md](docs/design.md) - Architecture and design decisions
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [CHANGELOG.md](CHANGELOG.md) - Version history and changes

## License 📄

See [LICENSE](LICENSE) file for details.

## Acknowledgments 🙏

- pgvector for PostgreSQL vector extension
- sentence-transformers for embeddings
- vLLM for fast LLM inference
- FastAPI for the web framework
- Apache Kafka for event streaming
