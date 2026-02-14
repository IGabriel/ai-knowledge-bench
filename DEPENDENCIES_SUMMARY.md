# 项目依赖说明 / Project Dependencies

[English](#english) | [中文](#中文)

---

## 中文

### 问题：除了 Python 类库之外，这个项目还需要安装什么依赖的组件？

**答案：本项目需要以下系统依赖组件：**

### 必需的系统组件

1. **Docker & Docker Compose**
   - 版本: Docker 20.10+, Docker Compose 2.0+
   - 用途: 容器编排，运行所有服务

2. **PostgreSQL 数据库 (带 pgvector 扩展)**
   - 版本: PostgreSQL 15+, pgvector 0.5.0+
   - 用途: 向量数据库，存储文档和嵌入向量

3. **Apache Kafka**
   - 版本: 3.5+ (KRaft 模式)
   - 用途: 消息队列，异步文档处理

4. **Redis**
   - 版本: 6.0+ (推荐 7.0+)
   - 用途: 缓存和会话管理

5. **vLLM** (可选但推荐)
   - 版本: 0.2.0+
   - 用途: 大语言模型推理，生成答案

### 快速安装方式

**方式 1: 使用 Docker Compose (推荐)**
```bash
cd deploy
docker compose up -d
```
这将自动启动 PostgreSQL、Kafka、Redis 等所有依赖服务。

**方式 2: 单独安装 vLLM**
```bash
pip install vllm
vllm serve Qwen/Qwen2.5-0.5B-Instruct --device cpu --port 8000
```

### 详细文档

- **完整依赖指南 (中文)**: [DEPENDENCIES_zh.md](DEPENDENCIES_zh.md)
- **Complete Dependencies Guide (English)**: [DEPENDENCIES.md](DEPENDENCIES.md)

---

## English

### Question: Besides Python libraries, what other dependent components need to be installed for this project?

**Answer: This project requires the following system dependencies:**

### Required System Components

1. **Docker & Docker Compose**
   - Version: Docker 20.10+, Docker Compose 2.0+
   - Purpose: Container orchestration, running all services

2. **PostgreSQL Database (with pgvector extension)**
   - Version: PostgreSQL 15+, pgvector 0.5.0+
   - Purpose: Vector database for documents and embeddings

3. **Apache Kafka**
   - Version: 3.5+ (KRaft mode)
   - Purpose: Message queue for asynchronous document processing

4. **Redis**
   - Version: 6.0+ (recommended 7.0+)
   - Purpose: Caching and session management

5. **vLLM** (Optional but recommended)
   - Version: 0.2.0+
   - Purpose: LLM inference for answer generation

### Quick Installation

**Option 1: Using Docker Compose (Recommended)**
```bash
cd deploy
docker compose up -d
```
This will automatically start all dependency services including PostgreSQL, Kafka, and Redis.

**Option 2: Install vLLM Separately**
```bash
pip install vllm
vllm serve Qwen/Qwen2.5-0.5B-Instruct --device cpu --port 8000
```

### Detailed Documentation

- **Complete Dependencies Guide (English)**: [DEPENDENCIES.md](DEPENDENCIES.md)
- **完整依赖指南 (中文)**: [DEPENDENCIES_zh.md](DEPENDENCIES_zh.md)

---

## Summary Table / 依赖组件汇总表

| Component / 组件 | Required / 必需 | Version / 版本 | Purpose / 用途 |
|-----------------|----------------|---------------|---------------|
| Docker | Yes / 是 | 20.10+ | Container orchestration / 容器编排 |
| Docker Compose | Yes / 是 | 2.0+ | Service orchestration / 服务编排 |
| PostgreSQL | Yes / 是 | 15+ | Document storage / 文档存储 |
| pgvector | Yes / 是 | 0.5.0+ | Vector search / 向量搜索 |
| Kafka | Yes / 是 | 3.5+ | Message queue / 消息队列 |
| Redis | Yes / 是 | 6.0+ | Caching / 缓存 |
| vLLM | Recommended / 推荐 | 0.2.0+ | LLM inference / LLM 推理 |
| Python | Optional* / 可选* | 3.11+ | Local development / 本地开发 |

\* Only required for local development outside Docker / 仅在 Docker 外本地开发时需要
