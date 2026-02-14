# 系统依赖指南

本文档详细说明了 AI Knowledge Bench 除 Python 类库之外所需的所有系统依赖组件。

## 概述

AI Knowledge Bench 需要多个外部组件才能正常运行。这些组件可以原生安装在您的系统上，也可以通过 Docker 运行（推荐）。

## 必需的系统依赖

### 1. Docker 和 Docker Compose

**用途**: 容器编排和运行所有服务

**版本要求**:
- Docker: 20.10+ (推荐: 24.0+)
- Docker Compose: 2.0+ (v2 语法)

**安装方法**:

**Ubuntu/Debian**:
```bash
# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 验证安装
docker --version
docker compose version
```

**macOS**:
```bash
# 安装 Docker Desktop
brew install --cask docker

# 或从官网下载: https://www.docker.com/products/docker-desktop
```

**Windows**:
- 从 https://www.docker.com/products/docker-desktop 下载并安装 Docker Desktop
- 启用 WSL 2 后端以获得更好的性能

**为什么需要**: Docker Compose 将所有服务（PostgreSQL、Kafka、Redis、Web API、Worker）作为容器进行编排，简化了设置过程并确保环境一致性。

---

### 2. PostgreSQL 数据库（带 pgvector 扩展）

**用途**: 向量数据库，用于存储嵌入向量和文档数据

**版本要求**: PostgreSQL 15+ 配合 pgvector 0.5.0+

**Docker 部署** (推荐):
```yaml
# 已在 deploy/docker-compose.yml 中配置
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: bench_user
      POSTGRES_PASSWORD: bench_pass
      POSTGRES_DB: ai_knowledge_bench
    ports:
      - "5432:5432"
```

**原生安装** (Ubuntu/Debian):
```bash
# 安装 PostgreSQL
sudo apt-get update
sudo apt-get install -y postgresql-15 postgresql-server-dev-15

# 安装 pgvector 扩展
cd /tmp
git clone --branch v0.5.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# 启用扩展
sudo -u postgres psql -d ai_knowledge_bench -c "CREATE EXTENSION vector;"
```

**macOS**:
```bash
# 安装 PostgreSQL
brew install postgresql@15

# 安装 pgvector
brew install pgvector

# 启动 PostgreSQL
brew services start postgresql@15
```

**为什么需要**: 存储文档元数据、文档块和向量嵌入以进行相似性搜索。pgvector 扩展提供了对嵌入向量的高效最近邻搜索功能。

---

### 3. Apache Kafka

**用途**: 消息队列，用于异步文档处理

**版本要求**: 3.5+ (使用 KRaft 模式，不需要 Zookeeper)

**Docker 部署** (推荐):
```yaml
# 已在 deploy/docker-compose.yml 中配置
services:
  kafka:
    image: apache/kafka:3.7.0
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    ports:
      - "9092:9092"
```

**原生安装** (Ubuntu/Debian):
```bash
# 下载 Kafka
cd /tmp
wget https://downloads.apache.org/kafka/3.7.0/kafka_2.13-3.7.0.tgz
tar -xzf kafka_2.13-3.7.0.tgz
sudo mv kafka_2.13-3.7.0 /opt/kafka

# 配置 KRaft 模式
cd /opt/kafka
KAFKA_CLUSTER_ID="$(bin/kafka-storage.sh random-uuid)"
bin/kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c config/kraft/server.properties

# 启动 Kafka
bin/kafka-server-start.sh config/kraft/server.properties
```

**macOS**:
```bash
# 通过 Homebrew 安装
brew install kafka

# 启动 Kafka
brew services start kafka
```

**为什么需要**: Kafka 处理异步文档处理任务。当文档上传时，事件被发送到 Kafka 主题，工作进程消费这些事件来执行提取、分块和嵌入操作。

---

### 4. Redis

**用途**: 缓存和会话管理

**版本要求**: 6.0+ (推荐: 7.0+)

**Docker 部署** (推荐):
```yaml
# 已在 deploy/docker-compose.yml 中配置
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

**原生安装** (Ubuntu/Debian):
```bash
# 安装 Redis
sudo apt-get update
sudo apt-get install -y redis-server

# 启动 Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# 验证
redis-cli ping
```

**macOS**:
```bash
# 通过 Homebrew 安装
brew install redis

# 启动 Redis
brew services start redis
```

**为什么需要**: Redis 用于缓存嵌入结果、存储临时会话数据以及协调分布式工作进程。

---

### 5. vLLM (可选但推荐)

**用途**: 大语言模型推理，用于生成答案

**版本要求**: 0.2.0+

**安装方法**:
```bash
# 安装 vLLM
pip install vllm

# 运行 vLLM 服务器 (CPU 模式)
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --dtype auto \
  --device cpu \
  --max-model-len 2048 \
  --port 8000

# 如果有 GPU，可以使用 GPU 模式
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --dtype auto \
  --device cuda \
  --max-model-len 4096 \
  --port 8000
```

**系统要求**:
- **CPU 模式**: 8GB+ 内存，现代 CPU
- **GPU 模式**: NVIDIA GPU 配备 8GB+ 显存，CUDA 11.8+

**可选模型**:
- 小型: `Qwen/Qwen2.5-0.5B-Instruct` (~500MB)
- 中型: `Qwen/Qwen2.5-1.5B-Instruct` (~1.5GB)
- 大型: `Qwen/Qwen2.5-3B-Instruct` (~3GB)

**为什么需要**: vLLM 提供语言模型，用于根据检索到的文档块生成自然语言答案。它提供与 OpenAI 兼容的 API 接口。

---

## 可选依赖

### Python 3.11+

如果在 Docker 外运行组件：

**安装方法** (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
```

**macOS**:
```bash
brew install python@3.11
```

### 构建工具

用于编译某些 Python 包：

**Ubuntu/Debian**:
```bash
sudo apt-get install -y build-essential libpq-dev
```

**macOS**:
```bash
xcode-select --install
```

---

## 部署选项

### 选项 1: Docker Compose (推荐)

所有依赖项都在容器中运行：

```bash
cd deploy
docker compose up -d
```

**优点**:
- 设置简单，无需手动安装依赖
- 环境一致
- 清理方便

**缺点**:
- 需要 Docker
- 资源使用较高

### 选项 2: 混合模式 (vLLM 单独运行)

在 Docker 中运行 PostgreSQL、Kafka、Redis；单独运行 vLLM：

```bash
# 启动核心服务
cd deploy
docker compose up -d postgres kafka redis web_api worker_ingest

# 单独运行 vLLM
pip install vllm
vllm serve Qwen/Qwen2.5-0.5B-Instruct --device cpu --port 8000
```

**优点**:
- 灵活地在不同硬件上运行 vLLM
- 更容易调试 vLLM 问题

**缺点**:
- 设置更复杂

### 选项 3: 原生安装

原生安装所有依赖：

**优点**:
- 最佳性能
- 精细控制

**缺点**:
- 设置复杂
- 环境特定问题
- 难以复制

---

## 最低系统要求

### 开发环境 (Docker Compose):
- **CPU**: 4 核
- **内存**: 最低 8GB，推荐 16GB
- **磁盘**: 20GB 可用空间
- **操作系统**: Linux、macOS、Windows 10+ 配备 WSL 2

### 生产环境:
- **CPU**: 8+ 核
- **内存**: 最低 32GB，推荐 64GB
- **磁盘**: 100GB+ SSD
- **GPU**: NVIDIA GPU 配备 16GB+ 显存 (用于 vLLM)
- **网络**: 1Gbps+ (用于分布式部署)

---

## 验证安装

检查所有依赖是否正常工作：

```bash
# 验证设置
bash validate.sh

# 检查 Docker 服务
cd deploy
docker compose ps

# 测试各个服务
docker compose exec postgres psql -U bench_user -d ai_knowledge_bench -c "SELECT version();"
docker compose exec kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092
docker compose exec redis redis-cli ping

# 测试 vLLM
curl http://localhost:8000/v1/models

# 测试 Web API
curl http://localhost:8080/health
```

---

## 故障排除

### Docker 问题

**"无法连接到 Docker 守护进程"**:
```bash
# 启动 Docker
sudo systemctl start docker  # Linux
# 或在 macOS/Windows 上重启 Docker Desktop
```

**"端口已被占用"**:
```bash
# 查找并终止占用端口的进程
sudo lsof -i :5432  # 或 :9092, :6379, :8080
sudo kill -9 <PID>
```

### PostgreSQL 问题

**"找不到 pgvector 扩展"**:
```bash
# 使用正确的镜像重新构建
cd deploy
docker compose down
docker compose up -d postgres
```

### Kafka 问题

**"连接 Kafka 被拒绝"**:
```bash
# 检查 Kafka 是否运行
docker compose logs kafka

# 重新创建 Kafka
docker compose rm -sf kafka
docker compose up -d kafka
```

### vLLM 问题

**"内存不足"**:
```bash
# 使用更小的模型
vllm serve Qwen/Qwen2.5-0.5B-Instruct --device cpu --max-model-len 1024

# 或减少上下文长度
vllm serve Qwen/Qwen2.5-1.5B-Instruct --device cpu --max-model-len 2048
```

---

## 总结

| 组件 | 是否必需 | 版本要求 | 用途 |
|------|---------|---------|------|
| Docker | 是 | 20.10+ | 容器编排 |
| Docker Compose | 是 | 2.0+ | 服务编排 |
| PostgreSQL | 是 | 15+ | 文档和元数据存储 |
| pgvector | 是 | 0.5.0+ | 向量相似性搜索 |
| Kafka | 是 | 3.5+ | 异步处理 |
| Redis | 是 | 6.0+ | 缓存和会话 |
| vLLM | 推荐 | 0.2.0+ | LLM 推理 |
| Python | 可选* | 3.11+ | 本地开发 |

\* 仅在 Docker 外进行本地开发时需要

---

## 依赖组件详细说明

### Docker 的作用
Docker 和 Docker Compose 是本项目的核心依赖。它们：
- 简化了多个复杂组件的安装和配置
- 确保开发和生产环境的一致性
- 提供服务隔离和资源管理
- 使得项目可以在不同操作系统上运行

### PostgreSQL + pgvector 的作用
PostgreSQL 是关系型数据库，存储：
- 文档元数据（标题、上传时间、文件类型等）
- 文档块（分块后的文本内容）
- 分块配置（chunk profiles）

pgvector 扩展增加了向量存储和搜索能力：
- 存储文档块的嵌入向量（默认 384 维）
- 执行高效的最近邻搜索（基于余弦相似度）
- 支持 ivfflat 和 hnsw 索引

### Kafka 的作用
Kafka 作为消息队列系统，实现：
- **异步处理**: 文档上传后立即返回，后台处理
- **解耦架构**: Web API 和 Worker 通过消息通信
- **可扩展性**: 可以启动多个 Worker 处理文档
- **可靠性**: 消息持久化，失败可以重试

主要的 Kafka 主题：
- `document.ingest.requested`: 文档摄取请求
- `document.reindex.requested`: 重新索引请求

### Redis 的作用
Redis 提供高速缓存功能：
- **嵌入缓存**: 缓存已计算的文档块嵌入向量
- **会话管理**: 存储用户会话信息
- **任务协调**: Worker 之间的协调和锁机制
- **临时数据**: 存储临时处理状态

### vLLM 的作用
vLLM 是高性能的 LLM 推理引擎：
- **答案生成**: 基于检索到的文档块生成自然语言答案
- **流式输出**: 支持 SSE 流式响应，实时显示生成的文本
- **OpenAI 兼容**: 提供与 OpenAI API 兼容的接口
- **高效推理**: 使用 PagedAttention 等技术优化推理性能

---

## 依赖安装顺序建议

如果选择原生安装，建议按以下顺序安装：

1. **Docker & Docker Compose** (如果使用 Docker 方式)
   ```bash
   # 安装 Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```

2. **PostgreSQL + pgvector**
   ```bash
   # Docker 方式最简单
   docker run -d --name postgres \
     -e POSTGRES_USER=bench_user \
     -e POSTGRES_PASSWORD=bench_pass \
     -e POSTGRES_DB=ai_knowledge_bench \
     -p 5432:5432 \
     pgvector/pgvector:pg16
   ```

3. **Kafka**
   ```bash
   # Docker 方式
   docker run -d --name kafka \
     -e KAFKA_NODE_ID=1 \
     -e KAFKA_PROCESS_ROLES=broker,controller \
     -p 9092:9092 \
     apache/kafka:3.7.0
   ```

4. **Redis**
   ```bash
   # Docker 方式
   docker run -d --name redis \
     -p 6379:6379 \
     redis:7-alpine
   ```

5. **Python 环境和依赖**
   ```bash
   # 创建虚拟环境
   python3.11 -m venv venv
   source venv/bin/activate
   
   # 安装 Python 依赖
   pip install -r requirements.txt
   ```

6. **vLLM** (最后安装，因为需要下载模型)
   ```bash
   pip install vllm
   vllm serve Qwen/Qwen2.5-0.5B-Instruct --device cpu --port 8000
   ```

---

更多信息请参阅：
- [README.md](README.md) - 完整项目文档
- [QUICKSTART.md](QUICKSTART.md) - 快速启动指南
- [docs/design.md](docs/design.md) - 架构设计详情
- [DEPENDENCIES.md](DEPENDENCIES.md) - 英文版依赖说明
