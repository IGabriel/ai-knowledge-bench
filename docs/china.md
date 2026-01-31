# Mainland China Setup (Mirrors + ModelScope)

This guide is for running this repo on a machine in mainland China.

## 1) Docker: use registry mirrors

If pulling images from Docker Hub is slow, configure Docker daemon mirrors.

Linux example (`/etc/docker/daemon.json`):

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://mirror.ccs.tencentyun.com"
  ]
}
```

Restart Docker after editing.

## 2) Python/pip: use domestic PyPI mirrors

### Local (host) pip

Recommended `pip` config (user-level):

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn
```

You can switch to Aliyun if you prefer:

```bash
pip config set global.index-url https://mirrors.aliyun.com/pypi/simple
pip config set global.trusted-host mirrors.aliyun.com
```

### Docker build-time pip + apt mirrors

This repo supports mirrors during Docker builds via `.env`:

- `APT_MIRROR` (Debian apt mirror)
- `PIP_INDEX_URL` / `PIP_TRUSTED_HOST` (PyPI mirror)

Copy and edit `.env`:

```bash
cp .env.example .env
```

## 3) ModelScope: download models locally

In mainland China, downloading models from Hugging Face may be slow or blocked.

### vLLM (LLM weights)

Run vLLM separately (recommended). Use ModelScope to download weights to local disk, then run vLLM with a local path.

```bash
pip install modelscope vllm

# Find the model on https://modelscope.cn and replace <model_id>
modelscope download --model <model_id> --local_dir ./models/<model_name>

vllm serve ./models/<model_name> --device cpu --port 8000
```

Set in `.env`:

- `VLLM_BASE_URL=http://localhost:8000/v1`

### Embeddings (optional)

This repo mounts a host directory `./models` into containers at `/app/models`.

If you download an embedding model via ModelScope to `./models/<embedding_model>`, you can point the app to it:

- Set `EMBEDDING_MODEL=/app/models/<embedding_model>` in `.env`

## 4) Common port conflict (PostgreSQL)

If your host already uses `5432`, set in `.env`:

- `POSTGRES_HOST_PORT=5433`

Then access Postgres via `localhost:5433` on the host.
