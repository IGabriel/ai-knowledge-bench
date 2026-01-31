"""Document ingestion worker."""
import json
import sys
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import text

from packages.core.config import get_settings
from packages.core.database import get_session_maker, DocumentStatus, Document, DocumentSection, DocumentChunk
from packages.core.kafka_utils import KafkaMessageConsumer
from packages.core.loaders import load_document, compute_file_sha256
from packages.core.chunking import chunk_text
from packages.core.embeddings import get_embedding_generator
from packages.core.logging_config import setup_logging
from packages.core.retrieval import get_embedding_table_name

logger = setup_logging("worker_ingest")


def get_active_chunk_profile(db: Session) -> Dict[str, Any]:
    """Get active chunk profile from database."""
    from packages.core.database import ChunkProfile
    
    profile = db.query(ChunkProfile).filter(ChunkProfile.is_active == True).first()
    
    if not profile:
        # Create default profile if none exists
        settings = get_settings()
        profile = ChunkProfile(
            id=uuid4(),
            name="default",
            description="Default chunk profile",
            chunk_size=settings.default_chunk_size,
            chunk_overlap=settings.default_chunk_overlap,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(profile)
        db.commit()
        logger.info("Created default chunk profile")
    
    return {
        "id": profile.id,
        "name": profile.name,
        "chunk_size": profile.chunk_size,
        "chunk_overlap": profile.chunk_overlap
    }


def process_document(document_id: str, chunk_profile_id: str = None):
    """
    Process a document: load, section, chunk, embed.
    
    Args:
        document_id: Document UUID
        chunk_profile_id: Optional specific chunk profile ID
    """
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    try:
        # Get document
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document not found: {document_id}")
            return
        
        logger.info(f"Processing document: {doc.filename} (ID: {document_id})")
        
        # Update status to ingesting
        doc.status = DocumentStatus.INGESTING
        db.commit()
        
        # Get chunk profile
        if chunk_profile_id:
            from packages.core.database import ChunkProfile
            profile_obj = db.query(ChunkProfile).filter(ChunkProfile.id == chunk_profile_id).first()
            if not profile_obj:
                logger.error(f"Chunk profile not found: {chunk_profile_id}")
                chunk_profile = get_active_chunk_profile(db)
            else:
                chunk_profile = {
                    "id": profile_obj.id,
                    "name": profile_obj.name,
                    "chunk_size": profile_obj.chunk_size,
                    "chunk_overlap": profile_obj.chunk_overlap
                }
        else:
            chunk_profile = get_active_chunk_profile(db)
        
        logger.info(f"Using chunk profile: {chunk_profile['name']}")
        
        # Load document sections
        try:
            sections = load_document(doc.filepath)
            logger.info(f"Loaded {len(sections)} sections from document")
        except Exception as e:
            logger.error(f"Error loading document: {e}", exc_info=True)
            doc.status = DocumentStatus.FAILED
            doc.error_message = f"Failed to load document: {str(e)}"
            db.commit()
            return
        
        # Store sections
        section_records = []
        for section in sections:
            section_record = DocumentSection(
                id=uuid4(),
                document_id=doc.id,
                source_ref=section.source_ref,
                content=section.content,
                metadata_json=json.dumps(section.metadata) if section.metadata else None,
                created_at=datetime.utcnow()
            )
            db.add(section_record)
            section_records.append(section_record)
        
        db.commit()
        logger.info(f"Stored {len(section_records)} sections")
        
        # Chunk sections
        all_chunks = []
        for section_record in section_records:
            chunks = chunk_text(
                section_record.content,
                chunk_profile["chunk_size"],
                chunk_profile["chunk_overlap"],
                section_record.source_ref
            )
            
            for chunk_content, source_ref, chunk_index in chunks:
                chunk_record = DocumentChunk(
                    id=uuid4(),
                    document_id=doc.id,
                    section_id=section_record.id,
                    chunk_profile_id=chunk_profile["id"],
                    content=chunk_content,
                    source_ref=source_ref,
                    chunk_index=chunk_index,
                    created_at=datetime.utcnow()
                )
                db.add(chunk_record)
                all_chunks.append(chunk_record)
        
        db.commit()
        logger.info(f"Created {len(all_chunks)} chunks")
        
        # Generate embeddings
        if all_chunks:
            settings = get_settings()
            emb_gen = get_embedding_generator()
            
            # Get chunk contents
            chunk_contents = [chunk.content for chunk in all_chunks]
            
            # Generate embeddings in batches
            logger.info(f"Generating embeddings for {len(chunk_contents)} chunks...")
            embeddings = emb_gen.encode(chunk_contents, show_progress=True)
            
            # Store embeddings in appropriate table
            table_name = get_embedding_table_name(settings.embedding_model)
            
            logger.info(f"Storing embeddings in table: {table_name}")
            
            for chunk_record, embedding in zip(all_chunks, embeddings):
                # Insert embedding using raw SQL
                insert_sql = text(f"""
                    INSERT INTO {table_name} 
                    (id, chunk_id, embedding, embedding_model, chunk_profile_id, created_at)
                    VALUES (:id, :chunk_id, :embedding, :embedding_model, :chunk_profile_id, :created_at)
                """)
                
                db.execute(insert_sql, {
                    "id": str(uuid4()),
                    "chunk_id": str(chunk_record.id),
                    "embedding": embedding.tolist(),
                    "embedding_model": settings.embedding_model,
                    "chunk_profile_id": str(chunk_profile["id"]),
                    "created_at": datetime.utcnow()
                })
            
            db.commit()
            logger.info(f"Stored {len(embeddings)} embeddings")
        
        # Update document status to ready
        doc.status = DocumentStatus.READY
        db.commit()
        
        logger.info(f"Document processing complete: {doc.filename}")
    
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)
            db.commit()
    
    finally:
        db.close()


def handle_ingest_message(message: Dict[str, Any]):
    """Handle document ingest message from Kafka."""
    logger.info(f"Handling ingest message: {message}")
    
    document_id = message.get("document_id")
    chunk_profile_id = message.get("chunk_profile_id")
    
    if not document_id:
        logger.error("Missing document_id in message")
        return
    
    process_document(document_id, chunk_profile_id)


def handle_reindex_message(message: Dict[str, Any]):
    """Handle document reindex message from Kafka."""
    logger.info(f"Handling reindex message: {message}")
    
    document_id = message.get("document_id")
    chunk_profile_id = message.get("chunk_profile_id")
    
    if not document_id or not chunk_profile_id:
        logger.error("Missing document_id or chunk_profile_id in message")
        return
    
    # Reindex is similar to initial ingest but may need to cleanup old chunks first
    # For now, we'll just reprocess
    process_document(document_id, chunk_profile_id)


def main():
    """Main worker entry point."""
    settings = get_settings()
    
    logger.info("Starting ingestion worker...")
    logger.info(f"Kafka bootstrap servers: {settings.kafka_bootstrap_servers}")
    logger.info(f"Consumer group: {settings.kafka_consumer_group}")
    
    topics = [settings.kafka_topic_ingest, settings.kafka_topic_reindex]
    
    consumer = KafkaMessageConsumer(topics=topics)
    
    def message_handler(message: Dict[str, Any]):
        """Route message to appropriate handler."""
        topic = message.get("__topic__")  # We'll need to add this
        
        # Since we can't easily get topic from Kafka message in the handler,
        # we'll check message content
        if "chunk_profile_id" in message and message.get("chunk_profile_id"):
            # Likely a reindex message
            handle_reindex_message(message)
        else:
            # Regular ingest message
            handle_ingest_message(message)
    
    consumer.consume(message_handler)


if __name__ == "__main__":
    main()
