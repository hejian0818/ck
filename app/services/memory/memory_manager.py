"""Session and task memory storage."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.thresholds import ANCHOR_CONFIDENCE_STRONG
from app.models.anchor import Anchor
from app.models.qa_models import RetrievalResult
from app.storage.redis_client import RedisLike, get_redis_client, redis_decode, redis_key


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


class TaskMemory(BaseModel):
    """Progress memory for long-running tasks."""

    model_config = ConfigDict(extra="forbid")

    task_type: Literal["doc_generation", "qa"]
    repo_id: str
    progress: dict[str, str] = Field(default_factory=dict)
    generated_sections: list[str] = Field(default_factory=list)
    retry_count: dict[str, int] = Field(default_factory=dict)
    started_at: str
    last_updated_at: str
    status: Literal["in_progress", "completed", "failed"] = "in_progress"
    checkpoint_data: dict[str, Any] = Field(default_factory=dict)


class MemoryManager:
    """Manage session memory with Redis persistence when configured."""

    def __init__(self, redis_client: RedisLike | None = None) -> None:
        self._sessions: dict[str, AnchorMemory] = {}
        self._tasks: dict[str, TaskMemory] = {}
        self._redis = redis_client if redis_client is not None else get_redis_client()

    def get_anchor_memory(self, session_id: str) -> AnchorMemory:
        if self._redis is not None:
            memory = self._load_anchor_memory(session_id)
            if memory is not None:
                return memory
            memory = AnchorMemory()
            self._save_anchor_memory(session_id, memory)
            return memory
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
        self._save_anchor_memory(session_id, memory)

    def clear_memory(self, session_id: str) -> None:
        if self._redis is not None:
            self._redis.delete(self._anchor_key(session_id))
            return
        self._sessions.pop(session_id, None)

    def create_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
        section_ids: list[str] | None = None,
        checkpoint_data: dict[str, Any] | None = None,
    ) -> TaskMemory:
        now = self._timestamp()
        progress = {section_id: "pending" for section_id in (section_ids or [])}
        retry_count = {section_id: 0 for section_id in progress}
        task_memory = TaskMemory(
            task_type=task_type,
            repo_id=repo_id,
            progress=progress,
            retry_count=retry_count,
            started_at=now,
            last_updated_at=now,
            checkpoint_data=dict(checkpoint_data or {}),
        )
        self._save_task_memory(task_type, repo_id, task_memory)
        if self._redis is not None:
            return task_memory
        self._tasks[self._task_key(task_type, repo_id)] = task_memory
        return task_memory

    def get_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
    ) -> TaskMemory | None:
        if self._redis is not None:
            return self._load_task_memory(task_type, repo_id)
        return self._tasks.get(self._task_key(task_type, repo_id))

    def resume_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
    ) -> TaskMemory | None:
        return self.get_task_memory(task_type, repo_id)

    def update_task_progress(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
        section_id: str,
        status: Literal["pending", "done", "failed"],
        checkpoint: dict[str, Any] | None = None,
    ) -> TaskMemory:
        task_memory = self._require_task_memory(task_type, repo_id)
        task_memory.progress[section_id] = status
        task_memory.retry_count.setdefault(section_id, 0)
        if status == "done":
            if section_id not in task_memory.generated_sections:
                task_memory.generated_sections.append(section_id)
        elif status == "failed" and section_id in task_memory.generated_sections:
            task_memory.generated_sections.remove(section_id)

        if checkpoint:
            task_memory.checkpoint_data.update(checkpoint)

        if task_memory.progress and all(value == "done" for value in task_memory.progress.values()):
            task_memory.status = "completed"
        elif any(value == "failed" for value in task_memory.progress.values()):
            task_memory.status = "failed"
        else:
            task_memory.status = "in_progress"

        task_memory.last_updated_at = self._timestamp()
        self._save_task_memory(task_type, repo_id, task_memory)
        return task_memory

    def increment_task_retry(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
        section_id: str,
    ) -> TaskMemory:
        task_memory = self._require_task_memory(task_type, repo_id)
        next_retry_count = task_memory.retry_count.get(section_id, 0) + 1
        task_memory.retry_count[section_id] = next_retry_count
        if next_retry_count > 3:
            task_memory.progress[section_id] = "failed"
            task_memory.status = "failed"
        else:
            task_memory.progress.setdefault(section_id, "pending")
        task_memory.last_updated_at = self._timestamp()
        self._save_task_memory(task_type, repo_id, task_memory)
        return task_memory

    def complete_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> TaskMemory:
        task_memory = self._require_task_memory(task_type, repo_id)
        if checkpoint:
            task_memory.checkpoint_data.update(checkpoint)
        for section_id, status in list(task_memory.progress.items()):
            if status != "done":
                task_memory.progress[section_id] = "done"
            if section_id not in task_memory.generated_sections:
                task_memory.generated_sections.append(section_id)
        task_memory.status = "completed"
        task_memory.last_updated_at = self._timestamp()
        self._save_task_memory(task_type, repo_id, task_memory)
        return task_memory

    def clear_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
    ) -> None:
        if self._redis is not None:
            self._redis.delete(self._task_memory_key(task_type, repo_id))
            return
        self._tasks.pop(self._task_key(task_type, repo_id), None)

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
        self._save_anchor_memory(session_id, memory)

    def update_focus_memory(self, session_id: str, question: str) -> None:
        memory = self.get_anchor_memory(session_id)
        next_focus = self._normalize_focus(question)
        if not next_focus:
            return

        current_focus = memory.focus_memory.current_focus
        if not current_focus or self._is_focus_continuation(current_focus, next_focus):
            memory.focus_memory.current_focus = current_focus or next_focus
            self._save_anchor_memory(session_id, memory)
            return

        memory.focus_memory.current_focus = next_focus
        self._save_anchor_memory(session_id, memory)

    def _load_anchor_memory(self, session_id: str) -> AnchorMemory | None:
        if self._redis is None:
            return None
        raw = redis_decode(self._redis.get(self._anchor_key(session_id)))
        if raw is None:
            return None
        return AnchorMemory.model_validate_json(raw)

    def _save_anchor_memory(self, session_id: str, memory: AnchorMemory) -> None:
        if self._redis is None:
            return
        self._redis.set(
            self._anchor_key(session_id),
            memory.model_dump_json(),
            ex=settings.SESSION_MEMORY_TTL_SECONDS,
        )

    def _load_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
    ) -> TaskMemory | None:
        if self._redis is None:
            return None
        raw = redis_decode(self._redis.get(self._task_memory_key(task_type, repo_id)))
        if raw is None:
            return None
        return TaskMemory.model_validate_json(raw)

    def _save_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
        task_memory: TaskMemory,
    ) -> None:
        if self._redis is None:
            return
        self._redis.set(
            self._task_memory_key(task_type, repo_id),
            task_memory.model_dump_json(),
            ex=settings.TASK_MEMORY_TTL_SECONDS,
        )

    @staticmethod
    def _anchor_key(session_id: str) -> str:
        return redis_key("memory", "session", session_id)

    @staticmethod
    def _task_memory_key(task_type: Literal["doc_generation", "qa"], repo_id: str) -> str:
        return redis_key("memory", "task", task_type, repo_id)

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

    @staticmethod
    def _task_key(task_type: Literal["doc_generation", "qa"], repo_id: str) -> str:
        return f"{task_type}:{repo_id}"

    def _require_task_memory(
        self,
        task_type: Literal["doc_generation", "qa"],
        repo_id: str,
    ) -> TaskMemory:
        task_memory = self.get_task_memory(task_type, repo_id)
        if task_memory is None:
            raise KeyError(f"Task memory not found for {task_type}:{repo_id}")
        return task_memory

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

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
