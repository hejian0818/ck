"""Shared API dependencies."""

from __future__ import annotations

from app.core.config import settings
from app.services.memory.memory_manager import MemoryManager
from app.storage.repositories import GraphRepository

memory_manager = MemoryManager()


def get_graph_repository() -> GraphRepository:
    """Create a repository instance from settings."""

    return GraphRepository(settings.DATABASE_URL)
