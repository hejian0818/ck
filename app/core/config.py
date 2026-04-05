"""Application configuration."""

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
    EMBEDDING_PROVIDER: str = Field(default="sentence-transformer")
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-base-en-v1.5")
    EMBEDDING_BATCH_SIZE: int = Field(default=32)
    EMBEDDING_OPENAI_MODEL: str = Field(default="text-embedding-3-small")
    VECTOR_TOP_K_MODULES: int = Field(default=5)
    VECTOR_TOP_K_FILES: int = Field(default=10)
    VECTOR_TOP_K_SYMBOLS: int = Field(default=20)
    VECTOR_TOP_K_RELATIONS: int = Field(default=15)
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")
    LLM_API_BASE: str = Field(default="http://localhost:11434/v1")
    LLM_API_KEY: str = Field(default="dummy")
    LLM_MODEL: str = Field(default="qwen2.5-coder:7b")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
