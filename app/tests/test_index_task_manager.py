"""Index task manager tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.models.qa_models import RepoBuildResponse
from app.services.indexing.task_manager import IndexTaskManager


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 4, 17, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


class IndexTaskManagerTests(unittest.TestCase):
    def _result(self) -> RepoBuildResponse:
        return RepoBuildResponse(build_id="repo_test", status="success")

    def test_completed_tasks_expire_after_retention_window(self) -> None:
        clock = _Clock()
        manager = IndexTaskManager(retention_seconds=10, max_entries=100, clock=clock)
        task_id = manager.create_task()
        manager.mark_success(task_id, self._result())

        clock.advance(seconds=11)

        self.assertIsNone(manager.get_task(task_id))

    def test_running_tasks_are_not_removed_by_ttl(self) -> None:
        clock = _Clock()
        manager = IndexTaskManager(retention_seconds=10, max_entries=100, clock=clock)
        task_id = manager.create_task()
        manager.mark_running(task_id)

        clock.advance(seconds=11)

        task = manager.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.status, "running")

    def test_max_entries_prunes_oldest_completed_tasks(self) -> None:
        clock = _Clock()
        manager = IndexTaskManager(retention_seconds=0, max_entries=2, clock=clock)
        first = manager.create_task()
        manager.mark_success(first, self._result())
        clock.advance(seconds=1)
        second = manager.create_task()
        manager.mark_failed(second, "failed")
        clock.advance(seconds=1)
        third = manager.create_task()

        self.assertIsNone(manager.get_task(first))
        self.assertIsNotNone(manager.get_task(second))
        self.assertIsNotNone(manager.get_task(third))

    def test_list_tasks_filters_status_and_orders_newest_first(self) -> None:
        clock = _Clock()
        manager = IndexTaskManager(retention_seconds=0, max_entries=100, clock=clock)
        first = manager.create_task()
        manager.mark_success(first, self._result())
        clock.advance(seconds=1)
        second = manager.create_task()
        manager.mark_failed(second, "failed")
        clock.advance(seconds=1)
        third = manager.create_task()
        manager.mark_success(third, self._result())

        success_ids = [task.task_id for task in manager.list_tasks(status="success")]
        all_ids = [task.task_id for task in manager.list_tasks(limit=2)]

        self.assertEqual(success_ids, [third, first])
        self.assertEqual(all_ids, [third, second])


if __name__ == "__main__":
    unittest.main()
