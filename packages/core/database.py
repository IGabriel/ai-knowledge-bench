"""Database models and setup."""
import enum
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

from packages.core.config import get_settings

Base = declarative_base()


# Enums
class DocumentStatus(str, enum.Enum):
    """Document processing status."""

    UPLOADED = "uploaded"
    INGESTING = "ingesting"
    READY = "ready"
    FAILED = "failed"


class AnswerType(str, enum.Enum):
    """Expected answer type for evaluation."""

    FACTUAL = "factual"
    SUMMARY = "summary"
    COMPARISON = "comparison"
    PROCEDURAL = "procedural"


# Models
class Document(Base):
    """Document table."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    filename = Column(String(512), nullable=False)
    filepath = Column(String(1024), nullable=False)
    mime_type = Column(String(128), nullable=True)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(Enum(DocumentStatus), nullable=False, default=DocumentStatus.UPLOADED)
    error_message = Column(Text, nullable=True)
    metadata_json = Column("metadata", Text, nullable=True)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sections = relationship("DocumentSection", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentSection(Base):
    """Document sections with stable source_ref."""

    __tablename__ = "document_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    source_ref = Column(String(512), nullable=False)  # e.g., "page=5", "slide=3", "sheet=Summary"
    content = Column(Text, nullable=False)
    metadata_json = Column("metadata", Text, nullable=True)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="sections")

    # Indexes
    __table_args__ = (Index("ix_document_sections_document_id", "document_id"),)


class ChunkProfile(Base):
    """Chunk profile configuration."""

    __tablename__ = "chunk_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    chunk_size = Column(Integer, nullable=False)
    chunk_overlap = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chunks = relationship("DocumentChunk", back_populates="chunk_profile")


class DocumentChunk(Base):
    """Document chunks."""

    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("document_sections.id", ondelete="CASCADE"), nullable=True)
    chunk_profile_id = Column(UUID(as_uuid=True), ForeignKey("chunk_profiles.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    source_ref = Column(String(512), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    metadata_json = Column("metadata", Text, nullable=True)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="chunks")
    chunk_profile = relationship("ChunkProfile", back_populates="chunks")

    # Indexes
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        Index("ix_document_chunks_chunk_profile_id", "chunk_profile_id"),
    )


class Settings(Base):
    """Application settings."""

    __tablename__ = "settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    """Chat sessions."""

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Chat messages."""

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    citations = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    # Indexes
    __table_args__ = (Index("ix_chat_messages_session_id", "session_id"),)


class AuditLog(Base):
    """Audit log."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    action = Column(String(255), nullable=False)
    entity_type = Column(String(128), nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes
    __table_args__ = (Index("ix_audit_logs_created_at", "created_at"),)


class EvaluationRun(Base):
    """Evaluation run results."""

    __tablename__ = "evaluation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    dataset_name = Column(String(255), nullable=False)
    chunk_profile_id = Column(UUID(as_uuid=True), nullable=False)
    embedding_model = Column(String(255), nullable=False)
    llm_model = Column(String(255), nullable=False)
    top_k = Column(Integer, nullable=False)
    metrics = Column(Text, nullable=False)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Indexes
    __table_args__ = (Index("ix_evaluation_runs_created_at", "created_at"),)


# Database engine and session
def get_engine():
    """Get database engine."""
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session_maker():
    """Get session maker."""
    engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get database session (dependency injection for FastAPI)."""
    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database (create tables)."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
