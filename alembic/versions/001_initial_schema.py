"""Initial schema with pgvector support

Revision ID: 001
Revises: 
Create Date: 2026-01-30 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('filename', sa.String(512), nullable=False),
        sa.Column('filepath', sa.String(1024), nullable=False),
        sa.Column('mime_type', sa.String(128), nullable=True),
        sa.Column('file_size', sa.Integer, nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('status', sa.Enum('uploaded', 'ingesting', 'ready', 'failed', name='documentstatus'), nullable=False),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('metadata', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_documents_sha256', 'documents', ['sha256'], unique=True)
    
    # Create document_sections table
    op.create_table(
        'document_sections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_ref', sa.String(512), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('metadata', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_document_sections_document_id', 'document_sections', ['document_id'])
    
    # Create chunk_profiles table
    op.create_table(
        'chunk_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('chunk_size', sa.Integer, nullable=False),
        sa.Column('chunk_overlap', sa.Integer, nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_chunk_profiles_name', 'chunk_profiles', ['name'], unique=True)
    
    # Create document_chunks table
    op.create_table(
        'document_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('section_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('chunk_profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('source_ref', sa.String(512), nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('metadata', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_id'], ['document_sections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chunk_profile_id'], ['chunk_profiles.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_document_chunks_document_id', 'document_chunks', ['document_id'])
    op.create_index('ix_document_chunks_chunk_profile_id', 'document_chunks', ['chunk_profile_id'])
    
    # Create settings table
    op.create_table(
        'settings',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('value', sa.Text, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    
    # Create chat_sessions table
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    
    # Create chat_messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(32), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('citations', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_chat_messages_session_id', 'chat_messages', ['session_id'])
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('entity_type', sa.String(128), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('details', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    
    # Create evaluation_runs table
    op.create_table(
        'evaluation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dataset_name', sa.String(255), nullable=False),
        sa.Column('chunk_profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('embedding_model', sa.String(255), nullable=False),
        sa.Column('llm_model', sa.String(255), nullable=False),
        sa.Column('top_k', sa.Integer, nullable=False),
        sa.Column('metrics', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_evaluation_runs_created_at', 'evaluation_runs', ['created_at'])
    
    # Create embedding table for multilingual-e5-small (384 dimensions)
    op.create_table(
        'chunk_embeddings__multilingual_e5_small',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('chunk_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(384), nullable=False),
        sa.Column('embedding_model', sa.String(255), nullable=False),
        sa.Column('chunk_profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['chunk_id'], ['document_chunks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chunk_profile_id'], ['chunk_profiles.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_chunk_embeddings_multilingual_e5_small_chunk_id', 
                    'chunk_embeddings__multilingual_e5_small', ['chunk_id'])
    op.create_index('ix_chunk_embeddings_multilingual_e5_small_chunk_profile_id', 
                    'chunk_embeddings__multilingual_e5_small', ['chunk_profile_id'])
    
    # Create vector index using ivfflat (adjust lists parameter based on data size)
    # For ~10k documents x 300 pages x avg chunks, we'll start with reasonable default
    op.execute("""
        CREATE INDEX ix_chunk_embeddings_multilingual_e5_small_embedding_vector 
        ON chunk_embeddings__multilingual_e5_small 
        USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100)
    """)


def downgrade() -> None:
    op.drop_table('chunk_embeddings__multilingual_e5_small')
    op.drop_table('evaluation_runs')
    op.drop_table('audit_logs')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
    op.drop_table('settings')
    op.drop_table('document_chunks')
    op.drop_table('chunk_profiles')
    op.drop_table('document_sections')
    op.drop_table('documents')
    op.execute('DROP EXTENSION IF EXISTS vector')
