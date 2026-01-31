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
            "description": "系统与基础能力（健康检查、简单 UI）。",
        },
        {
            "name": TAGS_DOCUMENTS,
            "description": "文档上传与文档列表（触发异步入库/索引）。",
        },
        {
            "name": TAGS_CHUNK_PROFILES,
            "description": "分块策略配置（chunk size / overlap / 激活的 profile）。",
        },
        {
            "name": TAGS_REINDEX,
            "description": "重建索引（通过 Kafka 触发异步重处理）。",
        },
        {
            "name": TAGS_CHAT,
            "description": "检索 + RAG + LLM 的 SSE 流式对话接口。",
        },
    ],
)

settings = get_settings()

# Ensure upload directory exists
os.makedirs(settings.app_upload_dir, exist_ok=True)


# Pydantic models
class DocumentResponse(BaseModel):
    """文档接口的返回模型（轻量视图）。

    主要用于上传后回显，以及列表展示。
    如需观察“入库/索引进度”，请轮询 `GET /v1/documents` 并查看 `status`。
    """

    id: str = Field(..., description="文档 UUID。", examples=["14b1f61b-1842-455d-b31c-7f0882bb1729"])
    filename: str = Field(..., description="用户上传时的原始文件名。", examples=["README.md"])
    mime_type: Optional[str] = Field(
        None,
        description="客户端报告的 MIME type；不同客户端/浏览器可能为空。",
        examples=["text/markdown"],
    )
    file_size: int = Field(..., description="文件大小（字节）。", examples=[14225])
    status: str = Field(
        ...,
        description="入库/索引状态。常见值：uploaded / ingesting / ready / failed。",
        examples=["ingesting"],
    )
    created_at: str = Field(
        ...,
        description="文档记录创建时间（UTC，ISO 8601）。",
        examples=["2026-01-31T08:27:42.151214"],
    )
    id: str
    filename: str
    mime_type: Optional[str]
    file_size: int
    status: str
    created_at: str


class ChunkProfileCreate(BaseModel):
    """创建分块策略（chunk profile）的请求模型。

    chunk profile 用于控制：文档如何切分成 chunk，再对 chunk 做 embedding 并写入向量表。
    """

    name: str = Field(..., description="profile 名称（需唯一）。", examples=["default"])
    description: Optional[str] = Field(None, description="描述信息（可选）。", examples=["默认分块策略"])
    chunk_size: int = Field(..., description="chunk 大小（实现相关：可能是 token/字符的近似值）。", examples=[512])
    chunk_overlap: int = Field(
        ...,
        description="相邻 chunk 的重叠大小。",
        examples=[128],
    )


class ChunkProfileResponse(BaseModel):
    """chunk profile 的返回模型。"""

    id: str = Field(..., description="chunk profile UUID。")
    name: str = Field(..., description="profile 名称。")
    description: Optional[str] = Field(None, description="profile 描述。")
    chunk_size: int = Field(..., description="chunk 大小。")
    chunk_overlap: int = Field(..., description="chunk 重叠大小。")
    is_active: bool = Field(..., description="是否为当前激活的 profile。")
    created_at: str = Field(..., description="创建时间（UTC，ISO 8601）。")


class ReindexRequest(BaseModel):
    """触发重建索引的请求模型。

    重建索引含义：按指定 chunk profile 重新分块，并重新生成 embeddings 写入向量表。
    注意：此接口只负责“发消息触发”，不会同步做耗时计算；实际工作由 worker 异步完成（Kafka）。
    """

    chunk_profile_id: str = Field(..., description="用于重建索引的 chunk profile UUID。")
    embedding_model: Optional[str] = Field(
        None,
        description="可选：本次重建索引使用的 embedding 模型。为空则使用服务默认配置。",
        examples=["intfloat/multilingual-e5-small"],
    )
    document_ids: Optional[List[str]] = Field(
        None,
        description="可选：仅重建这些 document UUID；为空则重建全部 READY 文档。",
        examples=[["14b1f61b-1842-455d-b31c-7f0882bb1729"]],
    )


class ChatRequest(BaseModel):
    """对话请求模型（目前主要用于文档/参考）。

    说明：本文件实际实现的是 `GET /v1/chat/stream`（SSE 流式），并非 POST JSON。
    """

    query: str = Field(..., description="用户问题。", examples=["这个项目是做什么的？"])
    top_k: Optional[int] = Field(None, description="检索 top_k（返回 chunk 数）。", examples=[5])
    chunk_profile_id: Optional[str] = Field(
        None,
        description="可选：指定 chunk profile UUID；为空则使用当前激活 profile。",
    )


# Endpoints
@app.get(
    "/",
    response_class=HTMLResponse,
    tags=[TAGS_SYSTEM],
    summary="Web UI（HTML）",
    description=(
        "提供一个极简的单页 HTML UI，用于手工验证（上传 + 流式对话）。"
        "程序化调用请使用 /v1/* 接口，并查看 /docs 自动生成的 OpenAPI 文档。"
    ),
)
async def root():
    """返回一个极简 HTML UI。

    该页面仅用于快速验证：上传文件、尝试 SSE 流式对话。
    并不是一个完整的前端应用。
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
    summary="健康检查",
    description="存活探针（liveness）。服务进程正常时返回 200。",
)
async def health():
    """健康检查（liveness）。

    返回：`{"status": "ok"}`。
    """
    return {"status": "ok"}


@app.post(
    "/v1/documents",
    response_model=DocumentResponse,
    tags=[TAGS_DOCUMENTS],
    summary="上传文档",
    description=(
        "上传单个文档：保存到磁盘、写入 documents 表，并发送 ingest 事件到 Kafka。"
        "真正的解析/分块/embedding/写向量表由 worker 异步完成。"
        "\n\n去重策略：按文件 SHA-256 去重。若已存在相同 SHA-256 的文档，本次上传会删除重复文件并直接返回已存在的文档记录。"
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
    """上传文档并触发异步入库/索引。

    处理流程：
        1) 将上传的文件落盘到 `APP_UPLOAD_DIR`。
        2) 计算 SHA-256 并检查是否重复。
        3) 向 `documents` 表插入记录（初始 status=uploaded）。
        4) 向 Kafka 发布 ingest 消息，worker 将异步处理（解析→分块→embedding→写向量表）。

    参数：
        file: multipart 文件字段。
        db: SQLAlchemy 会话（依赖注入）。

    返回：
        DocumentResponse：文档基本信息与当前状态。

    备注：
        - 返回的 status 可能是 uploaded 或 ingesting（取决于 worker 消费速度）。
        - 进度查看：轮询 `GET /v1/documents` 或查看 worker 日志。
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
    summary="获取文档列表",
    description="从数据库读取文档列表（通过 skip/limit 做简单分页）。",
    responses={
        200: {"description": "文档列表。"},
    },
)
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取文档列表。

    参数：
        skip: offset。
        limit: 返回条数上限。
        db: SQLAlchemy 会话。

    返回：
        文档列表（当前实现未显式排序，顺序由数据库默认行为决定）。
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
    summary="获取分块策略列表",
    description="返回全部 chunk profiles；其中最多一个可处于激活状态（is_active=true）。",
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
    summary="创建分块策略",
    description=(
        "创建新的 chunk profile。新建 profile 默认不激活。"
        "要切换为生效策略，请调用 `POST /v1/chunk-profiles/{profile_id}/activate`。"
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
    """创建新的 chunk profile。

    参数：
        profile: 分块配置。
        db: SQLAlchemy 会话。

    返回：
        创建后的 profile。
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
    summary="激活分块策略",
    description=(
        "将指定 profile 设为激活，并将其他 profile 全部设为非激活。"
        "当检索/对话接口未显式指定 profile 时，会使用当前激活的 profile。"
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
    """激活 chunk profile。

    会更新数据库，保证仅一个 profile 处于 `is_active=true`。

    参数：
        profile_id: chunk profile UUID。
        db: SQLAlchemy 会话。

    返回：
        简单 JSON 确认激活成功。
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
    summary="触发重建索引",
    description=(
        "对选定文档发布 reindex 事件到 Kafka。"
        "若不传 document_ids，则默认对所有 READY 文档触发重建索引。"
    ),
    responses={
        200: {"description": "Reindex events published."},
    },
)
async def reindex_documents(
    request: ReindexRequest,
    db: Session = Depends(get_db)
):
    """触发重建索引（异步）。

    该接口仅负责发布 Kafka 消息，不会在请求周期内做 embedding 计算。

    参数：
        request: 目标 chunk_profile 以及可选过滤条件。
        db: SQLAlchemy 会话。

    返回：
        触发结果汇总（文档数量等）。
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
    summary="流式对话（SSE）",
    description=(
        "通过 Server-Sent Events (SSE) 流式返回对话结果。"
        "服务端会先从向量索引检索相关 chunk，构建 RAG prompt，然后从 LLM 流式输出 token。"
        "\n\n事件格式：每行 SSE 的 `data:` 是一个 JSON，对应不同 `type`（token/citations/error）。"
    ),
)
async def chat_stream(
    query: str = Query(...),
    top_k: Optional[int] = Query(None),
    chunk_profile_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """流式对话接口（SSE）。

    Query 参数：
        query: 用户问题。
        top_k: 可选，检索返回 chunk 数量。
        chunk_profile_id: 可选，指定 chunk profile；为空则使用当前激活 profile。

    SSE 流返回：
        - `data: {"type": "token", "content": "..."}`：逐 token 输出。
        - `data: {"type": "citations", "citations": [...]}`：最终引用来源。
        - `data: [DONE]`：结束标记。

    返回：
        `text/event-stream` 的 SSE 响应。
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
