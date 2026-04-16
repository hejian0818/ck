"""In-memory task tracking for repository indexing jobs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from app.core.config import settings
from app.models.qa_models import RepoBuildResponse, RepoBuildTaskStatusResponse


class IndexTaskManager:
    """Track background repository indexing task state."""

    def __init__(
        self,
        retention_seconds: int | None = None,
        max_entries: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._lock = Lock()
        self._tasks: dict[str, RepoBuildTaskStatusResponse] = {}
        self.retention_seconds = settings.INDEX_TASK_RETENTION_SECONDS if retention_seconds is None else retention_seconds
        self.max_entries = settings.INDEX_TASK_MAX_ENTRIES if max_entries is None else max_entries
        self._clock = clock or _now

    def create_task(self) -> str:
        """Create a queued task and return its id."""

        task_id = uuid4().hex
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            self._tasks[task_id] = RepoBuildTaskStatusResponse(
                task_id=task_id,
                status="queued",
                created_at=now,
                updated_at=now,
            )
            self._prune_locked(now)
        return task_id

    def mark_running(self, task_id: str) -> None:
        self._update(task_id, status="running")

    def mark_success(self, task_id: str, result: RepoBuildResponse) -> None:
        self._update(task_id, status="success", result=result, error=None)

    def mark_failed(self, task_id: str, error: str) -> None:
        self._update(task_id, status="failed", error=error)

    def get_task(self, task_id: str) -> RepoBuildTaskStatusResponse | None:
        with self._lock:
            self._prune_locked(self._clock())
            task = self._tasks.get(task_id)
            return task.model_copy(deep=True) if task is not None else None

    def _update(self, task_id: str, **changes: object) -> None:
        with self._lock:
            now = self._clock()
            self._prune_locked(now)
            task = self._tasks[task_id]
            self._tasks[task_id] = task.model_copy(update={"updated_at": now, **changes})
            self._prune_locked(now)

    def _prune_locked(self, now: datetime) -> None:
        if self.retention_seconds > 0:
            cutoff = now - timedelta(seconds=self.retention_seconds)
            expired_task_ids = [
                task_id
                for task_id, task in self._tasks.items()
                if task.status in {"success", "failed"} and task.updated_at < cutoff
            ]
            for task_id in expired_task_ids:
                del self._tasks[task_id]

        if self.max_entries <= 0 or len(self._tasks) <= self.max_entries:
            return

        removable = sorted(
            (
                task
                for task in self._tasks.values()
                if task.status in {"success", "failed"}
            ),
            key=lambda task: task.updated_at,
        )
        overflow = len(self._tasks) - self.max_entries
        for task in removable[:overflow]:
            self._tasks.pop(task.task_id, None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


index_task_manager = IndexTaskManager()
