"""Embedding generation utilities."""
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from typing import List, Optional

from packages.core.config import get_settings
from packages.core.logging_config import setup_logging

logger = setup_logging(__name__)


class EmbeddingGenerator:
    """Generate embeddings using sentence-transformers."""
    
    def __init__(
        self, 
        model_name: Optional[str] = None, 
        device: Optional[str] = None,
        batch_size: Optional[int] = None
    ):
        """
        Initialize embedding generator.
        
        Args:
            model_name: Model name (e.g., 'intfloat/multilingual-e5-small')
            device: Device to use ('cpu', 'cuda', etc.)
            batch_size: Batch size for encoding
        """
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.embedding_device
        self.batch_size = batch_size or settings.embedding_batch_size
        
        logger.info(f"Loading embedding model: {self.model_name} on {self.device}")
        self.model = SentenceTransformer(self.model_name, device=self.device)
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Model loaded, dimension: {self.dimension}")
    
    def encode(self, texts: List[str], show_progress: bool = False) -> np.ndarray:
        """
        Encode texts into embeddings.
        
        Args:
            texts: List of texts to encode
            show_progress: Whether to show progress bar
            
        Returns:
            Numpy array of embeddings
        """
        if not texts:
            return np.array([])
        
        # For multilingual-e5 models, add "query: " prefix for queries
        # and "passage: " prefix for documents (we'll use passage for all chunks)
        processed_texts = [f"passage: {text}" for text in texts]
        
        embeddings = self.model.encode(
            processed_texts,
            batch_size=self.batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=True  # Important for cosine similarity
        )
        
        return embeddings
    
    def encode_query(self, query: str) -> np.ndarray:
        """
        Encode a query text into embedding.
        
        Args:
            query: Query text
            
        Returns:
            Numpy array of embedding
        """
        # For queries, use "query: " prefix for multilingual-e5
        processed_query = f"query: {query}"
        
        embedding = self.model.encode(
            [processed_query],
            batch_size=1,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        
        return embedding[0]


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    if vec1.ndim == 1:
        vec1 = vec1.reshape(1, -1)
    if vec2.ndim == 1:
        vec2 = vec2.reshape(1, -1)
    
    # If already normalized, dot product = cosine similarity
    return float(np.dot(vec1, vec2.T)[0][0])


# Singleton instance
_embedding_generator: Optional[EmbeddingGenerator] = None


def get_embedding_generator() -> EmbeddingGenerator:
    """Get or create singleton embedding generator."""
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator
