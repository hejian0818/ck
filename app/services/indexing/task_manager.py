"""Task tracking for repository indexing jobs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from app.core.config import settings
from app.models.qa_models import RepoBuildResponse, RepoBuildTaskStatusResponse
from app.storage.redis_client import RedisLike, get_redis_client, redis_decode, redis_key


class IndexTaskManager:
    """Track background repository indexing task state."""

    def __init__(
        self,
        retention_seconds: int | None = None,
        max_entries: int | None = None,
        clock: Callable[[], datetime] | None = None,
        redis_client: RedisLike | None = None,
    ) -> None:
        self._lock = Lock()
        self._tasks: dict[str, RepoBuildTaskStatusResponse] = {}
        self.retention_seconds = settings.INDEX_TASK_RETENTION_SECONDS if retention_seconds is None else retention_seconds
        self.max_entries = settings.INDEX_TASK_MAX_ENTRIES if max_entries is None else max_entries
        self._clock = clock or _now
        self._redis = redis_client if redis_client is not None else get_redis_client()

    def create_task(self) -> str:
        """Create a queued task and return its id."""

        task_id = uuid4().hex
        now = self._clock()
        task = RepoBuildTaskStatusResponse(
            task_id=task_id,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        if self._redis is not None:
            self._save_redis_task(task)
            self._prune_redis(now)
            return task_id

        with self._lock:
            self._prune_locked(now)
            self._tasks[task_id] = task
            self._prune_locked(now)
        return task_id

    def mark_running(self, task_id: str) -> None:
        self._update(task_id, status="running")

    def mark_success(self, task_id: str, result: RepoBuildResponse) -> None:
        self._update(task_id, status="success", result=result, error=None)

    def mark_failed(self, task_id: str, error: str) -> None:
        self._update(task_id, status="failed", error=error)

    def get_task(self, task_id: str) -> RepoBuildTaskStatusResponse | None:
        if self._redis is not None:
            self._prune_redis(self._clock())
            return self._load_redis_task(task_id)

        with self._lock:
            self._prune_locked(self._clock())
            task = self._tasks.get(task_id)
            return task.model_copy(deep=True) if task is not None else None

    def list_tasks(self, status: str | None = None, limit: int = 50) -> list[RepoBuildTaskStatusResponse]:
        """Return recent tasks, newest first."""

        if self._redis is not None:
            self._prune_redis(self._clock())
            tasks = self._list_redis_tasks()
            if status is not None:
                tasks = [task for task in tasks if task.status == status]
            if limit > 0:
                tasks = tasks[:limit]
            return tasks

        with self._lock:
            self._prune_locked(self._clock())
            tasks = list(self._tasks.values())
            if status is not None:
                tasks = [task for task in tasks if task.status == status]
            tasks.sort(key=lambda task: task.updated_at, reverse=True)
            if limit > 0:
                tasks = tasks[:limit]
            return [task.model_copy(deep=True) for task in tasks]

    def _update(self, task_id: str, **changes: object) -> None:
        if self._redis is not None:
            now = self._clock()
            self._prune_redis(now)
            task = self._load_redis_task(task_id)
            if task is None:
                raise KeyError(task_id)
            self._save_redis_task(task.model_copy(update={"updated_at": now, **changes}))
            self._prune_redis(now)
            return

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

    def _save_redis_task(self, task: RepoBuildTaskStatusResponse) -> None:
        if self._redis is None:
            return
        ttl = self.retention_seconds if task.status in {"success", "failed"} and self.retention_seconds > 0 else None
        self._redis.set(self._task_key_redis(task.task_id), task.model_dump_json(), ex=ttl)
        self._redis.zadd(self._index_key_redis(), {task.task_id: task.updated_at.timestamp()})

    def _load_redis_task(self, task_id: str) -> RepoBuildTaskStatusResponse | None:
        if self._redis is None:
            return None
        raw = redis_decode(self._redis.get(self._task_key_redis(task_id)))
        if raw is None:
            self._redis.zrem(self._index_key_redis(), task_id)
            return None
        return RepoBuildTaskStatusResponse.model_validate_json(raw)

    def _list_redis_tasks(self) -> list[RepoBuildTaskStatusResponse]:
        if self._redis is None:
            return []
        tasks: list[RepoBuildTaskStatusResponse] = []
        for raw_task_id in self._redis.zrevrange(self._index_key_redis(), 0, -1):
            task_id = redis_decode(raw_task_id)
            if task_id is None:
                continue
            task = self._load_redis_task(task_id)
            if task is not None:
                tasks.append(task)
        return tasks

    def _prune_redis(self, now: datetime) -> None:
        if self._redis is None:
            return
        tasks = self._list_redis_tasks()
        if self.retention_seconds > 0:
            cutoff = now - timedelta(seconds=self.retention_seconds)
            for task in tasks:
                if task.status in {"success", "failed"} and task.updated_at < cutoff:
                    self._redis.delete(self._task_key_redis(task.task_id))
                    self._redis.zrem(self._index_key_redis(), task.task_id)
            tasks = self._list_redis_tasks()

        if self.max_entries <= 0 or len(tasks) <= self.max_entries:
            return

        removable = sorted(
            (task for task in tasks if task.status in {"success", "failed"}),
            key=lambda task: task.updated_at,
        )
        overflow = len(tasks) - self.max_entries
        for task in removable[:overflow]:
            self._redis.delete(self._task_key_redis(task.task_id))
            self._redis.zrem(self._index_key_redis(), task.task_id)

    @staticmethod
    def _task_key_redis(task_id: str) -> str:
        return redis_key("index-task", task_id)

    @staticmethod
    def _index_key_redis() -> str:
        return redis_key("index-task", "index")


def _now() -> datetime:
    return datetime.now(timezone.utc)


index_task_manager = IndexTaskManager()
