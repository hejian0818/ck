"""In-memory session anchor storage."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.models.anchor import Anchor


class AnchorMemory(BaseModel):
    """Per-session anchor memory."""

    model_config = ConfigDict(extra="forbid")

    current_anchor: Anchor | None = None


class MemoryManager:
    """Manage anchor memory in process memory."""

    def __init__(self) -> None:
        self._sessions: dict[str, AnchorMemory] = {}

    def get_anchor_memory(self, session_id: str) -> AnchorMemory:
        return self._sessions.setdefault(session_id, AnchorMemory())

    def update_anchor_memory(self, session_id: str, anchor: Anchor) -> None:
        self._sessions[session_id] = AnchorMemory(current_anchor=anchor)

    def clear_memory(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
