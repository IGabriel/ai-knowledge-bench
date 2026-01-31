"""FastAPI web application."""
import sys
from pathlib import Path
import os
import shutil
from datetime import datetime
from uuid import uuid4
from typing import List, Optional
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from packages.core.config import get_settings
from packages.core.database import (
    get_db,
    Document,
    DocumentStatus,
    ChunkProfile,
    get_session_maker,
)
from packages.core.loaders import compute_file_sha256
from packages.core.kafka_utils import send_ingest_event, send_reindex_event
from packages.core.retrieval import retrieve_chunks, format_citations, build_rag_context
from packages.core.vllm_client import get_vllm_client, build_rag_prompt
from packages.core.logging_config import setup_logging

logger = setup_logging("web_api")

TAGS_SYSTEM = "System"
TAGS_DOCUMENTS = "Documents"
TAGS_CHUNK_PROFILES = "Chunk Profiles"
TAGS_REINDEX = "Reindex"
TAGS_CHAT = "Chat"

app = FastAPI(
    title="AI Knowledge Bench",
    description="RAG knowledge assistant with evaluation harness",
    version="0.1.0",
    openapi_tags=[
        {
            "name": TAGS_SYSTEM,
            "description": "System and basic capabilities (health checks, minimal UI).",
        },
        {
            "name": TAGS_DOCUMENTS,
            "description": "Upload and list documents (triggers async ingest/index).",
        },
        {
            "name": TAGS_CHUNK_PROFILES,
            "description": "Chunking strategy config (chunk size / overlap / active profile).",
        },
        {
            "name": TAGS_REINDEX,
            "description": "Rebuild index (triggers async reprocessing via Kafka).",
        },
        {
            "name": TAGS_CHAT,
            "description": "Retrieval + RAG + LLM streaming chat endpoint (SSE).",
        },
    ],
)

settings = get_settings()

# Ensure upload directory exists
os.makedirs(settings.app_upload_dir, exist_ok=True)


# Pydantic models
class DocumentResponse(BaseModel):
    """Response model for document APIs (lightweight view).

    Primarily used for echoing back after upload and for list views.
    To observe ingest/index progress, poll `GET /v1/documents` and check `status`.
    """

    id: str = Field(..., description="Document UUID.", examples=["14b1f61b-1842-455d-b31c-7f0882bb1729"])
    filename: str = Field(..., description="Original filename provided by the client.", examples=["README.md"])
    mime_type: Optional[str] = Field(
        None,
        description="Client-reported MIME type; may be empty depending on browser/client.",
        examples=["text/markdown"],
    )
    file_size: int = Field(..., description="File size in bytes.", examples=[14225])
    status: str = Field(
        ...,
        description="Ingest/index status. Common values: uploaded / ingesting / ready / failed.",
        examples=["ingesting"],
    )
    created_at: str = Field(
        ...,
        description="Created timestamp (UTC, ISO 8601).",
        examples=["2026-01-31T08:27:42.151214"],
    )
    id: str
    filename: str
    mime_type: Optional[str]
    file_size: int
    status: str
    created_at: str


class ChunkProfileCreate(BaseModel):
    """Request model for creating a chunk profile.

    A chunk profile controls how documents are split into chunks, then embedded and
    written into the vector table.
    """

    name: str = Field(..., description="Profile name (must be unique).", examples=["default"])
    description: Optional[str] = Field(None, description="Optional description.", examples=["Default chunking strategy"])
    chunk_size: int = Field(
        ...,
        description="Chunk size (implementation-dependent; approximate tokens/chars).",
        examples=[512],
    )
    chunk_overlap: int = Field(
        ...,
        description="Overlap size between adjacent chunks.",
        examples=[128],
    )


class ChunkProfileResponse(BaseModel):
    """Response model for a chunk profile."""

    id: str = Field(..., description="Chunk profile UUID.")
    name: str = Field(..., description="Profile name.")
    description: Optional[str] = Field(None, description="Profile description.")
    chunk_size: int = Field(..., description="Chunk size.")
    chunk_overlap: int = Field(..., description="Chunk overlap size.")
    is_active: bool = Field(..., description="Whether this is the currently active profile.")
    created_at: str = Field(..., description="Created timestamp (UTC, ISO 8601).")


class ReindexRequest(BaseModel):
    """Request model for triggering reindex.

    Reindex means: re-chunk using the given chunk profile, regenerate embeddings, and
    write them into the vector table.
    Note: this endpoint only publishes a trigger message; the heavy work is performed
    asynchronously by the worker (Kafka).
    """

    chunk_profile_id: str = Field(..., description="Chunk profile UUID to use for reindex.")
    embedding_model: Optional[str] = Field(
        None,
        description="Optional: embedding model to use for this reindex. If omitted, use the service default.",
        examples=["intfloat/multilingual-e5-small"],
    )
    document_ids: Optional[List[str]] = Field(
        None,
        description="Optional: only reindex these document UUIDs; if omitted, reindex all READY documents.",
        examples=[["14b1f61b-1842-455d-b31c-7f0882bb1729"]],
    )


class ChatRequest(BaseModel):
    """Chat request model (currently for documentation/reference).

    Note: this file implements `GET /v1/chat/stream` (SSE streaming), not a POST JSON endpoint.
    """

    query: str = Field(..., description="User question.", examples=["What does this project do?"])
    top_k: Optional[int] = Field(None, description="Retrieval top_k (number of chunks returned).", examples=[5])
    chunk_profile_id: Optional[str] = Field(
        None,
        description="Optional: specify a chunk profile UUID; if omitted, use the currently active profile.",
    )


# Endpoints
@app.get(
    "/",
    response_class=HTMLResponse,
    tags=[TAGS_SYSTEM],
    summary="Web UI (HTML)",
    description=(
        "Provides a minimal single-page HTML UI for manual verification (upload + streaming chat). "
        "For programmatic access, use the /v1/* APIs and see the OpenAPI docs at /docs."
    ),
)
async def root():
    """Return a minimal HTML UI.

    This page is only for quick manual testing: upload files and try SSE streaming chat.
    It is not a full-fledged frontend application.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Knowledge Bench</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-bottom: 20px;
            }
            h1 {
                color: #333;
                border-bottom: 3px solid #4CAF50;
                padding-bottom: 10px;
            }
            h2 {
                color: #555;
                margin-top: 30px;
            }
            .upload-section, .chat-section {
                margin: 20px 0;
            }
            input[type="file"], input[type="text"] {
                padding: 10px;
                margin: 10px 0;
                width: 100%;
                box-sizing: border-box;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            button {
                background-color: #4CAF50;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                margin: 5px;
            }
            button:hover {
                background-color: #45a049;
            }
            button:disabled {
                background-color: #ccc;
                cursor: not-allowed;
            }
            .message {
                padding: 10px;
                margin: 10px 0;
                border-radius: 4px;
            }
            .user-message {
                background-color: #e3f2fd;
                text-align: right;
            }
            .assistant-message {
                background-color: #f1f8e9;
            }
            .citations {
                background-color: #fff3cd;
                padding: 15px;
                margin: 10px 0;
                border-radius: 4px;
                border-left: 4px solid #ffc107;
            }
            .citation {
                margin: 8px 0;
                padding: 8px;
                background: white;
                border-radius: 3px;
            }
            #status {
                padding: 10px;
                margin: 10px 0;
                border-radius: 4px;
                display: none;
            }
            .status-success {
                background-color: #d4edda;
                color: #155724;
            }
            .status-error {
                background-color: #f8d7da;
                color: #721c24;
            }
            .loading {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid #f3f3f3;
                border-top: 3px solid #4CAF50;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <h1>🤖 AI Knowledge Bench</h1>
        
        <div class="container">
            <h2>📄 Upload Document</h2>
            <div class="upload-section">
                <input type="file" id="fileInput" accept=".pdf,.docx,.pptx,.xlsx,.html,.md,.txt">
                <button onclick="uploadFile()">Upload</button>
                <div id="status"></div>
            </div>
        </div>
        
        <div class="container">
            <h2>💬 Chat</h2>
            <div class="chat-section">
                <input type="text" id="queryInput" placeholder="Ask a question..." onkeypress="if(event.key==='Enter') sendQuery()">
                <button onclick="sendQuery()">Send</button>
                <div id="chatMessages"></div>
                <div id="citations"></div>
            </div>
        </div>
        
        <script>
            async function uploadFile() {
                const fileInput = document.getElementById('fileInput');
                const status = document.getElementById('status');
                const file = fileInput.files[0];
                
                if (!file) {
                    showStatus('Please select a file', 'error');
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', file);
                
                showStatus('Uploading...', 'success');
                
                try {
                    const response = await fetch('/v1/documents', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        showStatus(`File uploaded successfully! Document ID: ${data.id}`, 'success');
                        fileInput.value = '';
                    } else {
                        const error = await response.text();
                        showStatus(`Upload failed: ${error}`, 'error');
                    }
                } catch (error) {
                    showStatus(`Upload error: ${error.message}`, 'error');
                }
            }
            
            async function sendQuery() {
                const queryInput = document.getElementById('queryInput');
                const chatMessages = document.getElementById('chatMessages');
                const citationsDiv = document.getElementById('citations');
                const query = queryInput.value.trim();
                
                if (!query) return;
                
                // Add user message
                addMessage(query, 'user');
                queryInput.value = '';
                
                // Add loading indicator
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'message assistant-message';
                loadingDiv.id = 'loading';
                loadingDiv.innerHTML = '<div class="loading"></div> Thinking...';
                chatMessages.appendChild(loadingDiv);
                
                try {
                    const response = await fetch(`/v1/chat/stream?query=${encodeURIComponent(query)}`);
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    
                    // Remove loading indicator
                    loadingDiv.remove();
                    
                    // Create message div for streaming response
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message assistant-message';
                    chatMessages.appendChild(messageDiv);
                    
                    let fullResponse = '';
                    let citations = [];
                    
                    while (true) {
                        const {value, done} = await reader.read();
                        if (done) break;
                        
                        const text = decoder.decode(value);
                        const lines = text.split('\\n');
                        
                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                const data = line.substring(6);
                                if (data === '[DONE]') continue;
                                
                                try {
                                    const parsed = JSON.parse(data);
                                    if (parsed.type === 'token') {
                                        fullResponse += parsed.content;
                                        messageDiv.textContent = fullResponse;
                                    } else if (parsed.type === 'citations') {
                                        citations = parsed.citations;
                                    }
                                } catch (e) {
                                    console.error('Parse error:', e);
                                }
                            }
                        }
                    }
                    
                    // Display citations
                    if (citations.length > 0) {
                        citationsDiv.innerHTML = '<h3>📚 Sources</h3>';
                        const citList = document.createElement('div');
                        citations.forEach((cit, idx) => {
                            const citDiv = document.createElement('div');
                            citDiv.className = 'citation';
                            citDiv.innerHTML = `
                                <strong>[${idx + 1}]</strong> ${cit.source_ref}<br>
                                <small>Document: ${cit.document_id.substring(0, 8)}... | Score: ${cit.score.toFixed(3)}</small><br>
                                <em>${cit.snippet}</em>
                            `;
                            citList.appendChild(citDiv);
                        });
                        const wrapper = document.createElement('div');
                        wrapper.className = 'citations';
                        wrapper.appendChild(citList);
                        citationsDiv.appendChild(wrapper);
                    }
                    
                } catch (error) {
                    loadingDiv.remove();
                    addMessage(`Error: ${error.message}`, 'assistant');
                }
            }
            
            function addMessage(content, role) {
                const chatMessages = document.getElementById('chatMessages');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}-message`;
                messageDiv.textContent = content;
                chatMessages.appendChild(messageDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
            
            function showStatus(message, type) {
                const status = document.getElementById('status');
                status.textContent = message;
                status.className = `status-${type}`;
                status.style.display = 'block';
                setTimeout(() => {
                    status.style.display = 'none';
                }, 5000);
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get(
    "/health",
    tags=[TAGS_SYSTEM],
    summary="Health check",
    description="Liveness probe. Returns 200 when the service process is running.",
)
async def health():
    """Health check (liveness).

    Returns: `{"status": "ok"}`.
    """
    return {"status": "ok"}


@app.post(
    "/v1/documents",
    response_model=DocumentResponse,
    tags=[TAGS_DOCUMENTS],
    summary="Upload document",
    description=(
        "Upload a single document: save to disk, insert into the documents table, and publish an ingest event to Kafka. "
        "Parsing/chunking/embedding/vector writes are done asynchronously by the worker."
        "\n\nDedup strategy: deduplicate by file SHA-256. If a document with the same SHA-256 already exists, this upload deletes the duplicate file and returns the existing document record."
    ),
    responses={
        200: {"description": "Document accepted (or deduplicated) and ingestion scheduled."},
        500: {"description": "Unexpected server error (see logs)."},
    },
)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a document and trigger async ingest/index.

    Flow:
        1) Persist the uploaded file to `APP_UPLOAD_DIR`.
        2) Compute SHA-256 and check for duplicates.
        3) Insert a record into the `documents` table (initial status=uploaded).
        4) Publish an ingest message to Kafka; the worker processes asynchronously
           (parse -> chunk -> embed -> write vectors).

    Args:
        file: Multipart file field.
        db: SQLAlchemy session (dependency injection).

    Returns:
        DocumentResponse: Basic document info and current status.

    Notes:
        - Returned status may be uploaded or ingesting (depends on worker speed).
        - To check progress: poll `GET /v1/documents` or check worker logs.
    """
    try:
        # Save file
        file_path = os.path.join(settings.app_upload_dir, f"{uuid4()}_{file.filename}")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Compute hash
        sha256 = compute_file_sha256(file_path)
        
        # Check if document already exists
        existing = db.query(Document).filter(Document.sha256 == sha256).first()
        if existing:
            # Remove duplicate file
            os.remove(file_path)
            logger.info(f"Document already exists: {existing.id}")
            return DocumentResponse(
                id=str(existing.id),
                filename=existing.filename,
                mime_type=existing.mime_type,
                file_size=existing.file_size,
                status=existing.status.value,
                created_at=existing.created_at.isoformat()
            )
        
        # Create document record
        doc = Document(
            id=uuid4(),
            filename=file.filename,
            filepath=file_path,
            mime_type=file.content_type,
            file_size=os.path.getsize(file_path),
            sha256=sha256,
            status=DocumentStatus.UPLOADED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        # Send Kafka event for ingestion
        send_ingest_event(str(doc.id))
        
        logger.info(f"Document uploaded: {doc.filename} (ID: {doc.id})")
        
        return DocumentResponse(
            id=str(doc.id),
            filename=doc.filename,
            mime_type=doc.mime_type,
            file_size=doc.file_size,
            status=doc.status.value,
            created_at=doc.created_at.isoformat()
        )
    
    except Exception as e:
        logger.error(f"Error uploading document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/v1/documents",
    response_model=List[DocumentResponse],
    tags=[TAGS_DOCUMENTS],
    summary="List documents",
    description="Read the document list from the database (simple pagination via skip/limit).",
    responses={
        200: {"description": "Document list."},
    },
)
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List documents.

    Args:
        skip: Offset.
        limit: Maximum number of items to return.
        db: SQLAlchemy session.

    Returns:
        List of documents (no explicit ordering; order depends on database default behavior).
    """
    docs = db.query(Document).offset(skip).limit(limit).all()
    
    return [
        DocumentResponse(
            id=str(doc.id),
            filename=doc.filename,
            mime_type=doc.mime_type,
            file_size=doc.file_size,
            status=doc.status.value,
            created_at=doc.created_at.isoformat()
        )
        for doc in docs
    ]


@app.get(
    "/v1/chunk-profiles",
    response_model=List[ChunkProfileResponse],
    tags=[TAGS_CHUNK_PROFILES],
    summary="List chunk profiles",
    description="Return all chunk profiles; at most one may be active (is_active=true).",
)
async def list_chunk_profiles(db: Session = Depends(get_db)):
    """List all chunk profiles."""
    profiles = db.query(ChunkProfile).all()
    
    return [
        ChunkProfileResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            chunk_size=p.chunk_size,
            chunk_overlap=p.chunk_overlap,
            is_active=p.is_active,
            created_at=p.created_at.isoformat()
        )
        for p in profiles
    ]


@app.post(
    "/v1/chunk-profiles",
    response_model=ChunkProfileResponse,
    tags=[TAGS_CHUNK_PROFILES],
    summary="Create chunk profile",
    description=(
        "Create a new chunk profile. Newly created profiles are inactive by default. "
        "To switch the active profile, call `POST /v1/chunk-profiles/{profile_id}/activate`."
    ),
    responses={
        400: {"description": "Profile name already exists."},
        200: {"description": "Chunk profile created."},
    },
)
async def create_chunk_profile(
    profile: ChunkProfileCreate,
    db: Session = Depends(get_db)
):
    """Create a new chunk profile.

    Args:
        profile: Chunking configuration.
        db: SQLAlchemy session.

    Returns:
        The created profile.
    """
    # Check if name already exists
    existing = db.query(ChunkProfile).filter(ChunkProfile.name == profile.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Profile name already exists")
    
    new_profile = ChunkProfile(
        id=uuid4(),
        name=profile.name,
        description=profile.description,
        chunk_size=profile.chunk_size,
        chunk_overlap=profile.chunk_overlap,
        is_active=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    
    return ChunkProfileResponse(
        id=str(new_profile.id),
        name=new_profile.name,
        description=new_profile.description,
        chunk_size=new_profile.chunk_size,
        chunk_overlap=new_profile.chunk_overlap,
        is_active=new_profile.is_active,
        created_at=new_profile.created_at.isoformat()
    )


@app.post(
    "/v1/chunk-profiles/{profile_id}/activate",
    tags=[TAGS_CHUNK_PROFILES],
    summary="Activate chunk profile",
    description=(
        "Set the specified profile as active and mark all other profiles as inactive. "
        "When retrieval/chat endpoints do not explicitly specify a profile, the currently active profile is used."
    ),
    responses={
        200: {"description": "Profile activated."},
        404: {"description": "Profile not found."},
    },
)
async def activate_chunk_profile(
    profile_id: str,
    db: Session = Depends(get_db)
):
    """Activate a chunk profile.

    Updates the database to ensure only one profile has `is_active=true`.

    Args:
        profile_id: Chunk profile UUID.
        db: SQLAlchemy session.

    Returns:
        A simple JSON acknowledgement.
    """
    profile = db.query(ChunkProfile).filter(ChunkProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    # Deactivate all profiles
    db.query(ChunkProfile).update({ChunkProfile.is_active: False})
    
    # Activate this profile
    profile.is_active = True
    profile.updated_at = datetime.utcnow()
    db.commit()
    
    return {"status": "activated", "profile_id": str(profile.id)}


@app.post(
    "/v1/reindex",
    tags=[TAGS_REINDEX],
    summary="Trigger reindex",
    description=(
        "Publish reindex events to Kafka for selected documents. "
        "If document_ids is omitted, reindex is triggered for all READY documents."
    ),
    responses={
        200: {"description": "Reindex events published."},
    },
)
async def reindex_documents(
    request: ReindexRequest,
    db: Session = Depends(get_db)
):
    """Trigger reindex (asynchronously).

    This endpoint only publishes Kafka messages; it does not run embedding computation
    within the request lifecycle.

    Args:
        request: Target chunk_profile and optional filters.
        db: SQLAlchemy session.

    Returns:
        Summary of what was triggered (e.g., document count).
    """
    # Get documents to reindex
    if request.document_ids:
        docs = db.query(Document).filter(Document.id.in_(request.document_ids)).all()
    else:
        # Reindex all ready documents
        docs = db.query(Document).filter(Document.status == DocumentStatus.READY).all()
    
    # Send reindex events
    for doc in docs:
        send_reindex_event(
            str(doc.id),
            request.chunk_profile_id,
            request.embedding_model
        )
    
    return {
        "status": "reindex_triggered",
        "document_count": len(docs),
        "chunk_profile_id": request.chunk_profile_id
    }


@app.get(
    "/v1/chat/stream",
    tags=[TAGS_CHAT],
    summary="Streaming chat (SSE)",
    description=(
        "Stream chat results via Server-Sent Events (SSE). "
        "The server retrieves relevant chunks from the vector index, builds a RAG prompt, then streams tokens from the LLM."
        "\n\nEvent format: each SSE `data:` line is a JSON object with a `type` (token/citations/error)."
    ),
)
async def chat_stream(
    query: str = Query(...),
    top_k: Optional[int] = Query(None),
    chunk_profile_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Streaming chat endpoint (SSE).

    Query params:
        query: User question.
        top_k: Optional number of chunks to retrieve.
        chunk_profile_id: Optional chunk profile; if omitted, uses the active profile.

    SSE stream:
        - `data: {"type": "token", "content": "..."}`: Token-by-token output.
        - `data: {"type": "citations", "citations": [...]}`: Final citations.
        - `data: [DONE]`: End marker.

    Returns:
        An SSE response with content type `text/event-stream`.
    """
    
    async def generate():
        try:
            # Get active chunk profile if not specified
            if not chunk_profile_id:
                active_profile = db.query(ChunkProfile).filter(ChunkProfile.is_active == True).first()
                if not active_profile:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'No active chunk profile'})}\n\n"
                    return
                profile_id = str(active_profile.id)
            else:
                profile_id = chunk_profile_id
            
            # Retrieve relevant chunks
            results = retrieve_chunks(
                db=db,
                query=query,
                chunk_profile_id=profile_id,
                top_k=top_k
            )
            
            if not results:
                yield f"data: {json.dumps({'type': 'token', 'content': 'No relevant information found.'})}\n\n"
                yield f"data: {json.dumps({'type': 'citations', 'citations': []})}\n\n"
                yield "data: [DONE]\n\n"
                return
            
            # Build context
            context = build_rag_context(results)
            
            # Build prompt
            messages = build_rag_prompt(query, context)
            
            # Stream response from vLLM
            vllm_client = get_vllm_client()
            
            for token in vllm_client.chat_stream(messages, max_tokens=512, temperature=0.7):
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            
            # Send citations
            citations = format_citations(results)
            yield f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"
            
            yield "data: [DONE]\n\n"
        
        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return EventSourceResponse(generate())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
