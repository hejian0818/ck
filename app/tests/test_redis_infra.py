"""Redis-backed infrastructure tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.anchor import Anchor
from app.models.qa_models import RepoBuildResponse
from app.services.indexing.task_manager import IndexTaskManager
from app.services.locks.distributed_lock import redis_lock
from app.services.memory.memory_manager import MemoryManager
from app.services.rate_limit.redis_rate_limiter import RateLimitExceeded, check_rate_limit


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str | int] = {}
        self.expirations: dict[str, int] = {}

    def set(self, name: str, value: str, ex: int | None = None, nx: bool = False) -> bool | None:
        if nx and name in self.values:
            return None
        self.values[name] = value
        if ex is not None:
            self.expirations[name] = ex
        return True

    def delete(self, *names: str) -> int:
        deleted = 0
        for name in names:
            if name in self.values:
                deleted += 1
                self.values.pop(name, None)
        return deleted

    def get(self, name: str) -> str | int | None:
        return self.values.get(name)

    def incr(self, name: str) -> int:
        value = int(self.values.get(name, 0)) + 1
        self.values[name] = value
        return value

    def expire(self, name: str, time: int) -> bool:
        self.expirations[name] = time
        return True

    def zadd(self, name: str, mapping: dict[str, float]) -> int:
        zset = self.values.setdefault(name, {})
        if not isinstance(zset, dict):
            raise TypeError("not a sorted set")
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = score
        return added

    def zrange(self, name: str, start: int, end: int) -> list[str]:
        members = self._sorted_members(name, reverse=False)
        return members[start:] if end == -1 else members[start : end + 1]

    def zrevrange(self, name: str, start: int, end: int) -> list[str]:
        members = self._sorted_members(name, reverse=True)
        return members[start:] if end == -1 else members[start : end + 1]

    def zrem(self, name: str, *values: str) -> int:
        zset = self.values.get(name)
        if not isinstance(zset, dict):
            return 0
        removed = 0
        for value in values:
            if value in zset:
                removed += 1
                zset.pop(value, None)
        return removed

    def _sorted_members(self, name: str, reverse: bool) -> list[str]:
        zset = self.values.get(name)
        if not isinstance(zset, dict):
            return []
        return [
            member
            for member, _score in sorted(
                zset.items(),
                key=lambda item: item[1],
                reverse=reverse,
            )
        ]


class RedisInfrastructureTests(unittest.TestCase):
    def test_redis_lock_acquires_and_releases_owned_lock(self) -> None:
        redis = _FakeRedis()

        with redis_lock("repo", ttl_seconds=30, redis_client=redis) as acquired:
            self.assertTrue(acquired)
            self.assertIn("ck:lock:repo", redis.values)

        self.assertNotIn("ck:lock:repo", redis.values)

    def test_redis_lock_reports_busy_lock(self) -> None:
        redis = _FakeRedis()
        redis.set("ck:lock:repo", "other", ex=30, nx=True)

        with redis_lock("repo", ttl_seconds=30, redis_client=redis) as acquired:
            self.assertFalse(acquired)

        self.assertEqual(redis.get("ck:lock:repo"), "other")

    def test_rate_limit_raises_after_limit(self) -> None:
        redis = _FakeRedis()

        with (
            patch("app.services.rate_limit.redis_rate_limiter.settings.RATE_LIMIT_ENABLED", True),
            patch("app.services.rate_limit.redis_rate_limiter.settings.RATE_LIMIT_REQUESTS", 1),
            patch("app.services.rate_limit.redis_rate_limiter.settings.RATE_LIMIT_WINDOW_SECONDS", 60),
        ):
            check_rate_limit("client", redis_client=redis)
            with self.assertRaises(RateLimitExceeded):
                check_rate_limit("client", redis_client=redis)

    def test_api_rate_limit_returns_429(self) -> None:
        redis = _FakeRedis()

        with (
            patch("app.services.rate_limit.redis_rate_limiter.settings.RATE_LIMIT_ENABLED", True),
            patch("app.services.rate_limit.redis_rate_limiter.settings.RATE_LIMIT_REQUESTS", 0),
            patch("app.services.rate_limit.redis_rate_limiter.get_redis_client", return_value=redis),
        ):
            response = TestClient(app).post("/metrics/reset")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["code"], "rate_limited")

    def test_memory_manager_persists_session_memory_in_redis(self) -> None:
        redis = _FakeRedis()
        first_manager = MemoryManager(redis_client=redis)
        first_manager.update_anchor_memory(
            "session-1",
            Anchor(level="file", source="explicit_file", confidence=0.8, file_id="F_demo"),
        )

        second_manager = MemoryManager(redis_client=redis)
        memory = second_manager.get_anchor_memory("session-1")

        self.assertIsNotNone(memory.current_anchor)
        self.assertEqual(memory.current_anchor.file_id, "F_demo")

    def test_index_task_manager_persists_task_state_in_redis(self) -> None:
        redis = _FakeRedis()
        first_manager = IndexTaskManager(redis_client=redis)
        task_id = first_manager.create_task()
        first_manager.mark_success(task_id, RepoBuildResponse(build_id="repo", status="success"))

        second_manager = IndexTaskManager(redis_client=redis)
        task = second_manager.get_task(task_id)

        self.assertIsNotNone(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.result.build_id, "repo")


if __name__ == "__main__":
    unittest.main()
