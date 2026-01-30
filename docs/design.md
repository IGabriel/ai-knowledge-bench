# Design Documentation

## Overview

This document describes the architectural decisions and implementation details of the AI Knowledge Bench RAG system.

## Chunk Profile System

### Concept

Chunk profiles allow users to experiment with different chunking strategies without reprocessing the entire knowledge base from scratch. Each profile defines:

- **chunk_size**: Maximum characters per chunk
- **chunk_overlap**: Characters to overlap between consecutive chunks
- **name**: Human-readable identifier
- **is_active**: Whether this profile is currently used for new ingestions

### Implementation

1. **Database Schema**:
   - `chunk_profiles` table stores profile configurations
   - `document_chunks` table has a foreign key to `chunk_profiles`
   - Embeddings are associated with specific chunk profiles

2. **Workflow**:
   ```
   User uploads document
   → Worker uses active profile to chunk
   → Chunks stored with profile_id
   → Embeddings generated and linked to profile_id
   → Retrieval filters by profile_id
   ```

3. **Profile Switching**:
   - Create new profile via API
   - Activate new profile
   - Trigger reindex of documents
   - Worker regenerates chunks with new profile
   - Old chunks remain for comparison

### Use Cases

- **Testing**: Compare small vs. large chunks for specific use cases
- **Optimization**: Iterate on chunk size to improve retrieval quality
- **A/B Testing**: Run parallel profiles and measure performance
- **Domain-specific**: Different profiles for technical docs vs. marketing content

## Embedding Strategy: Separate Tables Per Model (Strategy A)

### Rationale

We use **separate tables per embedding model** rather than a single table with model identifier or separate schemas/databases.

### Advantages

1. **Performance**: 
   - Dedicated indexes per model/dimension
   - No filtering overhead on model_id
   - Optimized vector index parameters per model

2. **Schema Flexibility**:
   - Different vector dimensions per model
   - Model-specific metadata
   - Easy to add model-specific optimizations

3. **Maintenance**:
   - Easy to drop old model tables
   - Clear separation of concerns
   - Simpler vacuum/analyze operations

4. **Migration**:
   - Can migrate models independently
   - No disruption to active models
   - A/B test new models easily

### Disadvantages

1. **Schema Complexity**: Need to create new table for each model
2. **Query Complexity**: Can't easily compare across models in single query
3. **Maintenance**: More tables to manage

### Table Naming Convention

```
chunk_embeddings__{model_slug}
```

Examples:
- `intfloat/multilingual-e5-small` → `chunk_embeddings__multilingual_e5_small`
- `sentence-transformers/all-MiniLM-L6-v2` → `chunk_embeddings__all_MiniLM_L6_v2`

### Table Schema

```sql
CREATE TABLE chunk_embeddings__multilingual_e5_small (
    id UUID PRIMARY KEY,
    chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    embedding vector(384) NOT NULL,  -- Dimension depends on model
    embedding_model VARCHAR(255) NOT NULL,
    chunk_profile_id UUID NOT NULL REFERENCES chunk_profiles(id),
    created_at TIMESTAMP NOT NULL
);

-- Indexes
CREATE INDEX idx_chunk_emb_multilingual_e5_small_chunk_id 
    ON chunk_embeddings__multilingual_e5_small(chunk_id);
CREATE INDEX idx_chunk_emb_multilingual_e5_small_chunk_profile 
    ON chunk_embeddings__multilingual_e5_small(chunk_profile_id);

-- Vector index (ivfflat or hnsw)
CREATE INDEX idx_chunk_emb_multilingual_e5_small_vector 
    ON chunk_embeddings__multilingual_e5_small 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);
```

### Adding New Models

1. Create migration with new table
2. Update embedding generator to support new model
3. Add table name mapping in retrieval code
4. Optionally: Add settings to track available models

## Strict Source Reference Matching

### Purpose

Evaluation requires **strict matching** of source references to ensure retrieved chunks are from the exact same location in the document as the expected answer.

### Matching Rules

A retrieved source matches an expected source if **BOTH** conditions are met:

1. **document_id** matches (UUID equality)
2. **source_ref** matches exactly (string equality)

### Source Reference Format

Format varies by document type:

| Document Type | Source Ref Format | Example |
|---------------|-------------------|---------|
| PDF | `page=N` | `page=5` |
| PPTX | `slide=N` | `slide=3` |
| XLSX | `sheet=NAME` | `sheet=Sales_Summary` |
| DOCX | `heading=TEXT` | `heading=Introduction` |
| HTML | `heading=TEXT` | `heading=Getting Started` |
| Markdown | `heading=TEXT` | `heading=API Reference` |
| TXT | `section=NAME` | `section=document_name` |

### Why Strict Matching?

1. **Precision**: Ensures chunks are from the correct section/page
2. **Evaluation Quality**: Prevents false positives from other parts of the document
3. **User Trust**: Citations point to exact locations
4. **Debugging**: Easy to verify retrieval correctness

### Example

Expected source:
```json
{
  "document_id": "123e4567-e89b-12d3-a456-426614174000",
  "source_ref": "page=5"
}
```

Retrieved sources:
```json
[
  {
    "document_id": "123e4567-e89b-12d3-a456-426614174000",
    "source_ref": "page=5"  // ✅ Match
  },
  {
    "document_id": "123e4567-e89b-12d3-a456-426614174000",
    "source_ref": "page=6"  // ❌ No match (different page)
  },
  {
    "document_id": "789e4567-e89b-12d3-a456-426614174000",
    "source_ref": "page=5"  // ❌ No match (different document)
  }
]
```

## Document Processing Pipeline

### Stages

1. **Upload**:
   - User uploads file via API
   - File saved to storage
   - Document record created with status=UPLOADED
   - SHA256 hash computed for deduplication
   - Kafka event emitted: `document.ingest.requested`

2. **Section Extraction**:
   - Worker loads document using appropriate loader
   - Content normalized to text
   - Sections extracted with stable source_ref
   - Sections stored in database

3. **Chunking**:
   - Each section split into chunks using active profile
   - Chunks stored with profile_id and source_ref
   - Chunk index tracks order within section

4. **Embedding**:
   - Chunk contents batched for efficiency
   - Embeddings generated using configured model
   - Stored in model-specific table
   - Document status updated to READY

### Idempotency

- Documents identified by SHA256 hash
- Duplicate uploads return existing document
- Reindex operations are idempotent (chunks replaced)

### Error Handling

- Failed documents marked with status=FAILED
- Error message stored for debugging
- Worker continues processing other documents
- Failed documents can be retried

## Retrieval and Ranking

### Query Processing

1. **Encode Query**:
   ```python
   query_embedding = encoder.encode_query("What is the revenue?")
   ```
   - For multilingual-e5 models, add "query: " prefix

2. **Vector Search**:
   ```sql
   SELECT chunk_id, document_id, source_ref, content,
          1 - (embedding <=> query_vector) as similarity
   FROM chunk_embeddings__model
   WHERE chunk_profile_id = active_profile
   ORDER BY embedding <=> query_vector
   LIMIT top_k
   ```
   - Uses pgvector's cosine distance operator `<=>`
   - Returns similarity score (1 - distance)

3. **Filter by Threshold**:
   - Only return chunks above similarity threshold
   - Default threshold: 0.7

4. **Build Context**:
   - Format chunks with source references
   - Limit total context size (~2000 tokens)
   - Preserve source attribution

### RAG Prompting

System prompt:
```
You are a helpful assistant that answers questions based on provided context.
Your answers must be grounded in the context provided. If the context doesn't 
contain enough information to answer the question, say so.
Always cite your sources using the [Source N] references provided in the context.
```

Context format:
```
[Source 1: page=5]
Content of first chunk...

[Source 2: page=7]
Content of second chunk...

Question: What is the revenue?
```

### Citation Extraction

- LLM encouraged to cite sources using [Source N] notation
- Post-processing maps citations to document_id + source_ref
- Returned with answer for user verification

## Evaluation Metrics

### Ingestion Metrics

**Embedding Coverage**:
```
coverage = total_retrieved / (num_questions * top_k)
```
- Should be ≥ 0.99
- Lower values indicate missing embeddings or retrieval issues

### Retrieval Metrics

**Recall@K**:
```
recall@k = (num_expected_sources_in_top_k) / num_expected_sources
```
- Strict source matching
- Averaged across all questions

**Mean Reciprocal Rank (MRR)**:
```
mrr = 1 / rank_of_first_match
```
- Measures how early correct source appears
- 0 if no match found

### End-to-End Metrics

**Semantic Similarity**:
```
similarity = cosine_similarity(expected_embedding, generated_embedding)
```
- Uses same embedding model as retrieval
- Measures answer quality

**Semantic Correct Rate**:
```
correct_rate = count(similarity >= threshold) / total_questions
```
- Binary correctness metric
- Default threshold: 0.75

**Citation Hit Rate**:
```
hit_rate = count(at_least_one_correct_source) / total_questions
```
- Measures if any expected source cited
- Strict source matching

### Composite Score

```
score = 0.30 * recall + 0.20 * mrr + 0.30 * semantic_sim + 0.20 * citation_hit
```

Weights chosen to balance:
- Retrieval quality (30% + 20% = 50%)
- Answer quality (30%)
- Citation accuracy (20%)

## Vector Index Tuning

### ivfflat vs. HNSW

**ivfflat** (Inverted File Flat):
- Faster insert
- Lower memory
- Good for < 1M vectors
- Used by default

**HNSW** (Hierarchical Navigable Small World):
- Faster query
- Higher memory
- Better for > 1M vectors
- Can be enabled in migration

### Index Parameters

**ivfflat**:
```sql
CREATE INDEX ON embeddings 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);
```
- `lists`: Number of clusters
- Rule of thumb: `sqrt(num_rows)`
- For 10K docs × 300 pages × 10 chunks = 30M chunks → lists ≈ 5477

**HNSW**:
```sql
CREATE INDEX ON embeddings 
USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);
```
- `m`: Number of connections per layer (16-32)
- `ef_construction`: Build-time parameter (64-200)

### Query Parameters

For better recall at query time:
```sql
SET ivfflat.probes = 10;  -- Default: 1, check more clusters
```

## Scalability Considerations

### Current Scale Target

- **Documents**: ~10,000
- **Pages per doc**: ~300 average
- **Chunks per page**: ~2-5
- **Total chunks**: ~6M - 15M
- **Embeddings**: Same as chunks

### Bottlenecks

1. **Embedding Generation**: 
   - CPU-bound, ~100-500 chunks/min
   - Solution: GPU, batch larger

2. **Vector Search**:
   - Memory-bound for index
   - Solution: HNSW index, more RAM, partitioning

3. **vLLM Inference**:
   - CPU inference slow (~5-20 tokens/sec)
   - Solution: GPU inference, quantization

### Scaling Strategies

**Horizontal Scaling**:
- Multiple worker_ingest instances (Kafka consumer groups)
- Multiple web_api instances (load balancer)
- Kafka partitioning for parallel processing

**Vertical Scaling**:
- More RAM for vector index
- GPU for embeddings and inference
- SSD for database

**Optimization**:
- Batch embedding generation
- Cache frequent queries
- Precompute common aggregations
- Use approximate nearest neighbor search

## Security Considerations

### Data Protection

- Documents stored on local filesystem (consider S3/object storage)
- Database credentials in environment variables
- SHA256 hashing for deduplication (not encryption)

### API Security

- No authentication in MVP (add JWT/OAuth for production)
- Rate limiting not implemented (add for production)
- File upload size limits enforced
- Input validation for SQL injection prevention

### Future Enhancements

- Add user authentication and authorization
- Implement role-based access control
- Encrypt sensitive documents at rest
- Add audit logging for compliance
- Implement API rate limiting
- Add CORS configuration for production

## Monitoring and Observability

### Metrics to Track

1. **Ingestion**:
   - Documents processed per minute
   - Ingestion success/failure rate
   - Average processing time per document
   - Queue depth (Kafka lag)

2. **Retrieval**:
   - Query latency (p50, p95, p99)
   - Retrieval success rate
   - Average chunks returned
   - Cache hit rate (if caching)

3. **System**:
   - CPU/Memory usage
   - Database connection pool
   - Kafka consumer lag
   - vLLM inference latency

### Logging

- Structured logging with JSON
- Log levels: DEBUG, INFO, WARNING, ERROR
- Context: request_id, user_id, document_id
- Centralized logging (e.g., ELK stack)

### Alerts

- Embedding coverage < 0.99
- Ingestion worker stopped
- Database connection failures
- vLLM service unavailable
- High query latency

## Future Enhancements

### Short Term

- [ ] Add user authentication
- [ ] Implement caching (Redis)
- [ ] Add more chunking strategies (semantic, sliding window)
- [ ] Support more embedding models
- [ ] Improve UI (React/Vue frontend)
- [ ] Add document deletion API

### Medium Term

- [ ] Multi-modal support (images, tables)
- [ ] Query understanding (intent detection, entity extraction)
- [ ] Result re-ranking (cross-encoder)
- [ ] Conversational context (multi-turn chat)
- [ ] Export/import knowledge base
- [ ] Admin dashboard

### Long Term

- [ ] Multi-tenancy support
- [ ] Distributed vector search (Milvus, Qdrant)
- [ ] Fine-tuning on domain data
- [ ] Active learning for evaluation
- [ ] Integration with external tools (Slack, Teams)
- [ ] Advanced analytics and insights
