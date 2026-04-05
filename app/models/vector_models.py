"""Models for vector indexing and retrieval."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Embedding(BaseModel):
    """Embedding payload stored in pgvector."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    object_id: str
    object_type: str
    embedding: list[float] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Single vector similarity search hit."""

    model_config = ConfigDict(extra="forbid")

    object_id: str
    object_type: str
    similarity: float
