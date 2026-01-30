"""Basic sanity tests for core functionality."""
import pytest
from pathlib import Path
import tempfile


def test_imports():
    """Test that core modules can be imported."""
    from packages.core import config
    from packages.core import database
    from packages.core import loaders
    from packages.core import chunking
    from packages.core import embeddings
    from packages.core import retrieval
    from packages.core import kafka_utils
    from packages.core import vllm_client
    
    assert config is not None
    assert database is not None


def test_config_loading():
    """Test configuration loading."""
    from packages.core.config import get_settings
    
    settings = get_settings()
    assert settings.database_url is not None
    assert settings.embedding_model is not None
    assert settings.default_chunk_size > 0


def test_chunking_basic():
    """Test basic chunking functionality."""
    from packages.core.chunking import chunk_text
    
    text = "This is a test sentence. " * 100
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20, source_ref="page=1")
    
    assert len(chunks) > 0
    assert all(isinstance(chunk, tuple) for chunk in chunks)
    assert all(len(chunk) == 3 for chunk in chunks)
    assert all(chunk[1] == "page=1" for chunk in chunks)


def test_document_loaders_exist():
    """Test that document loaders are available."""
    from packages.core.loaders import (
        load_pdf,
        load_docx,
        load_pptx,
        load_xlsx,
        load_html,
        load_markdown,
        load_txt,
        load_document
    )
    
    assert callable(load_pdf)
    assert callable(load_docx)
    assert callable(load_pptx)
    assert callable(load_xlsx)
    assert callable(load_html)
    assert callable(load_markdown)
    assert callable(load_txt)
    assert callable(load_document)


def test_section_class():
    """Test Section class."""
    from packages.core.loaders import Section
    
    section = Section("page=1", "Test content", {"key": "value"})
    assert section.source_ref == "page=1"
    assert section.content == "Test content"
    assert section.metadata["key"] == "value"
    
    section_dict = section.to_dict()
    assert section_dict["source_ref"] == "page=1"
    assert section_dict["content"] == "Test content"


def test_load_txt():
    """Test loading a simple text file."""
    from packages.core.loaders import load_txt
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("This is a test document.\nWith multiple lines.\n")
        temp_path = f.name
    
    try:
        sections = load_txt(temp_path)
        assert len(sections) == 1
        assert "test document" in sections[0].content
    finally:
        Path(temp_path).unlink()


def test_sha256_computation():
    """Test SHA256 hash computation."""
    from packages.core.loaders import compute_file_sha256
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test content")
        temp_path = f.name
    
    try:
        hash1 = compute_file_sha256(temp_path)
        hash2 = compute_file_sha256(temp_path)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex characters
    finally:
        Path(temp_path).unlink()


def test_database_models():
    """Test that database models are defined."""
    from packages.core.database import (
        Document,
        DocumentSection,
        DocumentChunk,
        ChunkProfile,
        ChatSession,
        ChatMessage,
        AuditLog,
        EvaluationRun
    )
    
    assert Document is not None
    assert DocumentSection is not None
    assert DocumentChunk is not None
    assert ChunkProfile is not None


def test_retrieval_result():
    """Test RetrievalResult class."""
    from packages.core.retrieval import RetrievalResult
    
    result = RetrievalResult(
        chunk_id="chunk-123",
        document_id="doc-456",
        source_ref="page=1",
        content="Test content",
        score=0.95,
        metadata={"key": "value"}
    )
    
    assert result.chunk_id == "chunk-123"
    assert result.document_id == "doc-456"
    assert result.score == 0.95
    
    result_dict = result.to_dict()
    assert result_dict["chunk_id"] == "chunk-123"
    assert result_dict["score"] == 0.95


def test_golden_set_loads():
    """Test that golden set file exists and can be loaded."""
    from packages.eval.run import load_golden_set
    
    golden_set_path = "eval/golden_set_v1.jsonl"
    if Path(golden_set_path).exists():
        items = load_golden_set(golden_set_path)
        assert len(items) == 50
        assert all("id" in item for item in items)
        assert all("question" in item for item in items)
        assert all("expected_answer" in item for item in items)
        assert all("expected_sources" in item for item in items)


def test_strict_source_match():
    """Test strict source matching logic."""
    from packages.eval.run import strict_source_match
    
    expected = [
        {"document_id": "doc-1", "source_ref": "page=5"},
        {"document_id": "doc-1", "source_ref": "page=7"}
    ]
    
    retrieved = [
        {"document_id": "doc-1", "source_ref": "page=5"},  # Match
        {"document_id": "doc-1", "source_ref": "page=6"},  # No match
        {"document_id": "doc-2", "source_ref": "page=5"}   # No match (different doc)
    ]
    
    hits, total = strict_source_match(expected, retrieved)
    assert hits == 1
    assert total == 2


def test_recall_calculation():
    """Test recall@k calculation."""
    from packages.eval.run import calculate_recall_at_k
    
    expected = [
        {"document_id": "doc-1", "source_ref": "page=5"}
    ]
    
    retrieved = [
        {"document_id": "doc-1", "source_ref": "page=5"},
        {"document_id": "doc-1", "source_ref": "page=6"}
    ]
    
    recall = calculate_recall_at_k(expected, retrieved, k=2)
    assert recall == 1.0
    
    recall = calculate_recall_at_k(expected, retrieved, k=1)
    assert recall == 1.0


def test_mrr_calculation():
    """Test MRR calculation."""
    from packages.eval.run import calculate_mrr
    
    expected = [
        {"document_id": "doc-1", "source_ref": "page=5"}
    ]
    
    # First match at position 2
    retrieved = [
        {"document_id": "doc-1", "source_ref": "page=3"},
        {"document_id": "doc-1", "source_ref": "page=5"},  # Match
        {"document_id": "doc-1", "source_ref": "page=7"}
    ]
    
    mrr = calculate_mrr(expected, retrieved)
    assert mrr == 0.5  # 1/2
    
    # No match
    retrieved_no_match = [
        {"document_id": "doc-1", "source_ref": "page=3"}
    ]
    
    mrr = calculate_mrr(expected, retrieved_no_match)
    assert mrr == 0.0
