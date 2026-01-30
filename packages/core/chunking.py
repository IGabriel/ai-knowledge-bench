"""Chunking strategies for documents."""
from typing import List, Tuple
import re


def chunk_text(
    text: str, chunk_size: int, chunk_overlap: int, source_ref: str
) -> List[Tuple[str, str, int]]:
    """
    Chunk text with overlap.
    
    Args:
        text: Text to chunk
        chunk_size: Maximum characters per chunk
        chunk_overlap: Overlap between chunks
        source_ref: Source reference for the text
        
    Returns:
        List of (chunk_content, source_ref, chunk_index) tuples
    """
    if not text or chunk_size <= 0:
        return []
    
    chunks = []
    start = 0
    chunk_index = 0
    
    while start < len(text):
        # Calculate end position
        end = start + chunk_size
        
        # If this is not the last chunk, try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings near the end
            sentence_end = max(
                text.rfind('. ', start, end),
                text.rfind('! ', start, end),
                text.rfind('? ', start, end),
                text.rfind('\n\n', start, end),
            )
            
            if sentence_end > start:
                end = sentence_end + 1
        
        # Extract chunk
        chunk = text[start:end].strip()
        
        if chunk:
            chunks.append((chunk, source_ref, chunk_index))
            chunk_index += 1
        
        # Move start position (with overlap)
        start = end - chunk_overlap
        
        # Ensure progress
        if start <= end - chunk_size:
            start = end
    
    return chunks


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences (simple implementation)."""
    # Simple sentence splitter
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_by_sentences(
    text: str, chunk_size: int, chunk_overlap: int, source_ref: str
) -> List[Tuple[str, str, int]]:
    """
    Chunk text by sentences, respecting chunk size.
    
    Args:
        text: Text to chunk
        chunk_size: Maximum characters per chunk
        chunk_overlap: Overlap in sentences (approximate)
        source_ref: Source reference
        
    Returns:
        List of (chunk_content, source_ref, chunk_index) tuples
    """
    sentences = split_into_sentences(text)
    if not sentences:
        return []
    
    chunks = []
    chunk_index = 0
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence_len = len(sentence)
        
        # If adding this sentence would exceed chunk_size, save current chunk
        if current_length + sentence_len > chunk_size and current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append((chunk_text, source_ref, chunk_index))
            chunk_index += 1
            
            # Calculate overlap (keep last few sentences)
            overlap_chars = 0
            overlap_sentences = []
            for sent in reversed(current_chunk):
                if overlap_chars + len(sent) <= chunk_overlap:
                    overlap_sentences.insert(0, sent)
                    overlap_chars += len(sent)
                else:
                    break
            
            current_chunk = overlap_sentences
            current_length = overlap_chars
        
        current_chunk.append(sentence)
        current_length += sentence_len
    
    # Add final chunk
    if current_chunk:
        chunk_text = ' '.join(current_chunk)
        chunks.append((chunk_text, source_ref, chunk_index))
    
    return chunks
