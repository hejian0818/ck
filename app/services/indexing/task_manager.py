"""In-memory task tracking for repository indexing jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.models.qa_models import RepoBuildResponse, RepoBuildTaskStatusResponse


class IndexTaskManager:
    """Track background repository indexing task state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[str, RepoBuildTaskStatusResponse] = {}

    def create_task(self) -> str:
        """Create a queued task and return its id."""

        task_id = uuid4().hex
        now = _now()
        with self._lock:
            self._tasks[task_id] = RepoBuildTaskStatusResponse(
                task_id=task_id,
                status="queued",
                created_at=now,
                updated_at=now,
            )
        return task_id

    def mark_running(self, task_id: str) -> None:
        self._update(task_id, status="running")

    def mark_success(self, task_id: str, result: RepoBuildResponse) -> None:
        self._update(task_id, status="success", result=result, error=None)

    def mark_failed(self, task_id: str, error: str) -> None:
        self._update(task_id, status="failed", error=error)

    def get_task(self, task_id: str) -> RepoBuildTaskStatusResponse | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.model_copy(deep=True) if task is not None else None

    def _update(self, task_id: str, **changes: object) -> None:
        with self._lock:
            task = self._tasks[task_id]
            self._tasks[task_id] = task.model_copy(update={"updated_at": _now(), **changes})


def _now() -> datetime:
    return datetime.now(timezone.utc)


index_task_manager = IndexTaskManager()
