"""In-memory session memory storage."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from app.core.thresholds import ANCHOR_CONFIDENCE_STRONG
from app.models.anchor import Anchor
from app.models.qa_models import RetrievalResult


class RetrievalMemory(BaseModel):
    """Per-session retrieval memory."""

    model_config = ConfigDict(extra="forbid")

    recent_object_ids: list[str] = Field(default_factory=list)
    recent_subgraph_summary: str = ""
    recent_evidence_summary: str = ""


class FocusMemory(BaseModel):
    """Per-session focus memory."""

    model_config = ConfigDict(extra="forbid")

    current_focus: str = ""


class AnchorMemory(BaseModel):
    """Per-session conversational memory."""

    model_config = ConfigDict(extra="forbid")

    current_anchor: Anchor | None = None
    retrieval_memory: RetrievalMemory = Field(default_factory=RetrievalMemory)
    focus_memory: FocusMemory = Field(default_factory=FocusMemory)


class MemoryManager:
    """Manage session memory in process memory."""

    def __init__(self) -> None:
        self._sessions: dict[str, AnchorMemory] = {}

    def get_anchor_memory(self, session_id: str) -> AnchorMemory:
        return self._sessions.setdefault(session_id, AnchorMemory())

    def update_anchor_memory(self, session_id: str, anchor: Anchor) -> None:
        memory = self.get_anchor_memory(session_id)
        if self._should_preserve_anchor(memory.current_anchor, anchor):
            return

        previous_target = self._anchor_target(memory.current_anchor)
        next_target = self._anchor_target(anchor)
        memory.current_anchor = anchor

        if previous_target and next_target and previous_target != next_target:
            memory.retrieval_memory = RetrievalMemory()

    def clear_memory(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def update_retrieval_memory(
        self,
        session_id: str,
        anchor: Anchor,
        retrieval_result: RetrievalResult,
        recent_subgraph_summary: str,
        recent_evidence_summary: str,
    ) -> None:
        memory = self.get_anchor_memory(session_id)
        previous_target = self._anchor_target(memory.current_anchor)
        next_target = self._anchor_target(anchor)
        if previous_target and next_target and previous_target != next_target:
            memory.retrieval_memory = RetrievalMemory()

        object_ids: list[str] = []
        if retrieval_result.current_object is not None:
            object_ids.append(retrieval_result.current_object.id)
        object_ids.extend(object_.id for object_ in retrieval_result.related_objects)
        memory.retrieval_memory = RetrievalMemory(
            recent_object_ids=list(dict.fromkeys(object_ids)),
            recent_subgraph_summary=recent_subgraph_summary,
            recent_evidence_summary=recent_evidence_summary,
        )

    def update_focus_memory(self, session_id: str, question: str) -> None:
        memory = self.get_anchor_memory(session_id)
        next_focus = self._normalize_focus(question)
        if not next_focus:
            return

        current_focus = memory.focus_memory.current_focus
        if not current_focus or self._is_focus_continuation(current_focus, next_focus):
            memory.focus_memory.current_focus = current_focus or next_focus
            return

        memory.focus_memory.current_focus = next_focus

    @staticmethod
    def _should_preserve_anchor(current_anchor: Anchor | None, next_anchor: Anchor) -> bool:
        return (
            current_anchor is not None
            and current_anchor.confidence >= ANCHOR_CONFIDENCE_STRONG
            and next_anchor.level == "none"
        )

    @staticmethod
    def _anchor_target(anchor: Anchor | None) -> str | None:
        if anchor is None or anchor.level == "none":
            return None
        return anchor.symbol_id or anchor.file_id or anchor.module_id

    @staticmethod
    def _normalize_focus(question: str) -> str:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", question).strip().lower()
        return normalized

    @classmethod
    def _is_focus_continuation(cls, current_focus: str, next_focus: str) -> bool:
        if current_focus in next_focus or next_focus in current_focus:
            return True

        current_tokens = set(current_focus.split())
        next_tokens = set(next_focus.split())
        if current_tokens and next_tokens:
            return bool(current_tokens.intersection(next_tokens))

        current_chars = {char for char in current_focus if not char.isspace()}
        next_chars = {char for char in next_focus if not char.isspace()}
        if not current_chars or not next_chars:
            return False
        overlap_ratio = len(current_chars.intersection(next_chars)) / max(
            min(len(current_chars), len(next_chars)),
            1,
        )
        return overlap_ratio >= 0.5
