"""Shared API dependencies."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.services.memory.memory_manager import MemoryManager
from app.storage.repositories import GraphRepository

memory_manager = MemoryManager()


@lru_cache(maxsize=1)
def get_graph_repository() -> GraphRepository:
    """Return a cached repository instance from settings."""

    return GraphRepository(settings.DATABASE_URL)
