"""Configuration management for AI Knowledge Bench."""
import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Database
    database_url: str = "postgresql://bench_user:bench_pass@localhost:5432/ai_knowledge_bench"
    pgvector_extension: str = "enabled"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_ingest: str = "document.ingest.requested"
    kafka_topic_reindex: str = "document.reindex.requested"
    kafka_consumer_group: str = "worker_ingest"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # vLLM
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_api_key: str = "EMPTY"
    vllm_model: str = "Qwen/Qwen2.5-0.5B-Instruct"

    # Embeddings
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_dimension: int = 384
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    app_log_level: str = "INFO"
    app_upload_dir: str = "./data/uploads"

    # Chunking
    default_chunk_size: int = 512
    default_chunk_overlap: int = 128

    # Retrieval
    default_top_k: int = 5
    default_similarity_threshold: float = 0.7

    # Evaluation
    eval_semantic_similarity_threshold: float = 0.75


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
