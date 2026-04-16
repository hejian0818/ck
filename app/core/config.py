"""Application configuration."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(default="postgresql://localhost/ck")
    VECTOR_DIMENSION: int = Field(default=768)
    ENABLE_VECTOR_INDEXING: bool = Field(default=True)
    EMBEDDING_PROVIDER: str = Field(default="sentence-transformer")
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-base-en-v1.5")
    EMBEDDING_BATCH_SIZE: int = Field(default=32)
    EMBEDDING_OPENAI_MODEL: str = Field(default="text-embedding-3-small")
    EMBEDDING_OPENAI_BASE_URL: str | None = Field(default=None)
    EMBEDDING_OPENAI_API_KEY: str | None = Field(default=None)
    VECTOR_TOP_K_MODULES: int = Field(default=5)
    VECTOR_TOP_K_FILES: int = Field(default=10)
    VECTOR_TOP_K_SYMBOLS: int = Field(default=20)
    VECTOR_TOP_K_RELATIONS: int = Field(default=15)
    DOC_PLANNER_MAX_FILES_PER_MODULE: int = Field(default=3)
    DOC_MODULE_SYMBOL_LIMIT: int = Field(default=8)
    DOC_RETRIEVAL_TOP_K: int = Field(default=10)
    DOC_VECTOR_TOP_K: int = Field(default=5)
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")
    LLM_API_BASE: str = Field(default="http://localhost:11434/v1")
    LLM_API_KEY: str = Field(default="dummy")
    LLM_MODEL: str = Field(default="qwen2.5-coder:7b")
    DOC_MAX_SECTIONS: int = Field(default=50)
    DOC_SECTION_MAX_TOKENS: int = Field(default=2000)
    DOC_DIAGRAM_ENABLED: bool = Field(default=True)
    CACHE_EMBEDDING_SIZE: int = Field(default=1000)
    CACHE_GRAPH_TTL: int = Field(default=60)
    LLM_MAX_RETRIES: int = Field(default=3)
    LLM_TIMEOUT: int = Field(default=30)
    API_KEY: str = Field(default="")
    REPO_SCAN_ALLOWED_ROOTS: str = Field(default="")
    REPO_SCAN_MAX_FILES: int = Field(default=5000)
    REPO_SCAN_MAX_FILE_BYTES: int = Field(default=1_000_000)


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
