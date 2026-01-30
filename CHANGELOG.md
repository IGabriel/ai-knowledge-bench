# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-30

### Added
- Initial release of AI Knowledge Bench
- FastAPI web application with HTML/JS UI
- Document upload and ingestion pipeline
- Support for PDF, DOCX, PPTX, XLSX, HTML, Markdown, and TXT formats
- PostgreSQL with pgvector for vector storage
- Kafka-based event-driven architecture
- Configurable chunk profiles for experimenting with chunking strategies
- Embedding generation with multilingual-e5-small (configurable)
- Vector similarity search and retrieval
- vLLM integration for local CPU inference
- SSE streaming chat endpoint
- Golden set evaluation harness with 50 test questions
- Comprehensive evaluation metrics (Recall@K, MRR, semantic similarity, citation hit rate)
- Docker Compose setup for local development
- Alembic database migrations
- Comprehensive documentation and design notes

### Features
- **Document Processing**: Automatic section extraction with stable source references
- **Chunking**: Dynamic chunking with overlap, sentence-boundary aware
- **Retrieval**: pgvector-based cosine similarity search with ivfflat index
- **RAG**: Context-aware prompting with citation enforcement
- **Evaluation**: Strict source reference matching for accurate quality measurement
- **Monitoring**: Structured logging throughout the pipeline

### Infrastructure
- PostgreSQL 16 with pgvector extension
- Apache Kafka 3.7 with KRaft mode (no Zookeeper)
- Redis for caching and session management
- Docker Compose for orchestration

### Documentation
- Complete README with quick start guide
- Design documentation explaining architecture
- API documentation via FastAPI Swagger
- Contributing guidelines
- Example golden set with 50 evaluation questions

[0.1.0]: https://github.com/IGabriel/ai-knowledge-bench/releases/tag/v0.1.0
