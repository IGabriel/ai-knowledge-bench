"""Retrieval logic using pgvector."""
from typing import List, Dict, Any, Optional
import json

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from packages.core.config import get_settings
from packages.core.embeddings import get_embedding_generator, cosine_similarity
from packages.core.logging_config import setup_logging

logger = setup_logging(__name__)


class RetrievalResult:
    """Single retrieval result."""
    
    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        source_ref: str,
        content: str,
        score: float,
        metadata: Optional[dict] = None
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.source_ref = source_ref
        self.content = content
        self.score = score
        self.metadata = metadata or {}
    
    def to_dict(self) -> dict:
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "source_ref": self.source_ref,
            "content": self.content,
            "score": float(self.score),
            "metadata": self.metadata
        }


def get_embedding_table_name(embedding_model: str) -> str:
    """Get embedding table name for a given model."""
    # Normalize model name to table name
    # e.g., 'intfloat/multilingual-e5-small' -> 'chunk_embeddings__multilingual_e5_small'
    model_slug = embedding_model.split('/')[-1].replace('-', '_').replace('.', '_')
    return f"chunk_embeddings__{model_slug}"


def retrieve_chunks(
    db: Session,
    query: str,
    chunk_profile_id: str,
    top_k: Optional[int] = None,
    similarity_threshold: Optional[float] = None,
    embedding_model: Optional[str] = None
) -> List[RetrievalResult]:
    """
    Retrieve relevant chunks using vector similarity.
    
    Args:
        db: Database session
        query: Query text
        chunk_profile_id: Chunk profile ID to filter by
        top_k: Number of results to return
        similarity_threshold: Minimum similarity score
        embedding_model: Embedding model to use
        
    Returns:
        List of RetrievalResult objects
    """
    settings = get_settings()
    top_k = top_k or settings.default_top_k
    similarity_threshold = similarity_threshold or settings.default_similarity_threshold
    embedding_model = embedding_model or settings.embedding_model
    
    # Get embedding generator
    emb_gen = get_embedding_generator()
    
    # Encode query
    query_embedding = emb_gen.encode_query(query)
    
    # Get embedding table name
    table_name = get_embedding_table_name(embedding_model)
    
    # Build query
    # Using cosine similarity (1 - cosine distance)
    # Note: pgvector's <=> operator returns cosine distance (0 = identical, 2 = opposite)
    # So we use (1 - (embedding <=> query_vector)) for similarity score
    
    query_sql = text(f"""
        SELECT 
            e.chunk_id,
            c.document_id,
            c.source_ref,
            c.content,
            c.metadata,
            1 - (e.embedding <=> :query_embedding) as similarity_score
        FROM {table_name} e
        JOIN document_chunks c ON e.chunk_id = c.id
        WHERE e.chunk_profile_id = :chunk_profile_id
        ORDER BY e.embedding <=> :query_embedding
        LIMIT :top_k
    """)
    
    # Execute query
    try:
        result = db.execute(
            query_sql,
            {
                "query_embedding": query_embedding.tolist(),
                "chunk_profile_id": chunk_profile_id,
                "top_k": top_k
            }
        )
        
        rows = result.fetchall()
        
        # Convert to RetrievalResult objects
        results = []
        for row in rows:
            chunk_id, doc_id, source_ref, content, metadata_json, score = row
            
            # Parse metadata if present
            metadata = {}
            if metadata_json:
                try:
                    metadata = json.loads(metadata_json)
                except:
                    pass
            
            # Filter by similarity threshold
            if score >= similarity_threshold:
                results.append(RetrievalResult(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    source_ref=source_ref,
                    content=content,
                    score=score,
                    metadata=metadata
                ))
        
        logger.info(
            f"Retrieved {len(results)} chunks for query (top_k={top_k}, "
            f"threshold={similarity_threshold})"
        )
        
        return results
    
    except Exception as e:
        logger.error(f"Error retrieving chunks: {e}", exc_info=True)
        raise


def format_citations(results: List[RetrievalResult]) -> List[Dict[str, Any]]:
    """
    Format retrieval results as citations.
    
    Args:
        results: List of RetrievalResult objects
        
    Returns:
        List of citation dictionaries
    """
    citations = []
    
    for result in results:
        citation = {
            "document_id": str(result.document_id),
            "source_ref": result.source_ref,
            "chunk_id": str(result.chunk_id),
            "score": float(result.score),
            "snippet": result.content[:200] + "..." if len(result.content) > 200 else result.content
        }
        citations.append(citation)
    
    return citations


def build_rag_context(results: List[RetrievalResult], max_tokens: int = 2000) -> str:
    """
    Build context from retrieval results for RAG.
    
    Args:
        results: List of RetrievalResult objects
        max_tokens: Maximum tokens (approximate, using chars/4)
        
    Returns:
        Context string
    """
    context_parts = []
    current_length = 0
    max_chars = max_tokens * 4  # Rough approximation
    
    for i, result in enumerate(results, 1):
        # Format each chunk with source reference
        chunk_text = f"[Source {i}: {result.source_ref}]\n{result.content}\n"
        
        if current_length + len(chunk_text) > max_chars:
            break
        
        context_parts.append(chunk_text)
        current_length += len(chunk_text)
    
    return "\n".join(context_parts)
