"""Memory manager tests."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import File
from app.models.qa_models import RetrievalResult
from app.services.memory.memory_manager import MemoryManager


class MemoryManagerTests(unittest.TestCase):
    def test_none_anchor_does_not_override_strong_anchor(self) -> None:
        manager = MemoryManager()
        session_id = "session-1"
        strong_anchor = Anchor(level="symbol", source="explicit_span", confidence=0.9, symbol_id="S_demo.entry")
        manager.update_anchor_memory(session_id, strong_anchor)

        manager.update_anchor_memory(
            session_id,
            Anchor(level="none", source="none", confidence=0.0),
        )

        self.assertEqual(manager.get_anchor_memory(session_id).current_anchor, strong_anchor)

    def test_anchor_change_clears_retrieval_memory_and_focus_switches(self) -> None:
        manager = MemoryManager()
        session_id = "session-2"
        first_anchor = Anchor(level="file", source="explicit_file", confidence=0.7, file_id="F_first")
        second_anchor = Anchor(level="file", source="explicit_file", confidence=0.7, file_id="F_second")
        first_file = File(
            id="F_first",
            name="first.py",
            path="first.py",
            module_id="M_demo",
            language="python",
            start_line=1,
            end_line=10,
        )

        manager.update_anchor_memory(session_id, first_anchor)
        manager.update_retrieval_memory(
            session_id=session_id,
            anchor=first_anchor,
            retrieval_result=RetrievalResult(
                anchor=first_anchor,
                current_object=first_file,
                object_scores={"F_first": 1.0},
            ),
            recent_subgraph_summary="first",
            recent_evidence_summary="evidence",
        )
        manager.update_focus_memory(session_id, "Explain first service flow")
        manager.update_focus_memory(session_id, "Explain first service implementation")
        manager.update_anchor_memory(session_id, second_anchor)

        memory = manager.get_anchor_memory(session_id)
        self.assertEqual(memory.retrieval_memory.recent_object_ids, [])
        self.assertEqual(memory.focus_memory.current_focus, "explain first service flow")

        manager.update_focus_memory(session_id, "How does parser adapter work")
        self.assertEqual(
            manager.get_anchor_memory(session_id).focus_memory.current_focus,
            "how does parser adapter work",
        )

    def test_task_memory_tracks_progress_and_resume_state(self) -> None:
        manager = MemoryManager()

        created = manager.create_task_memory(
            task_type="doc_generation",
            repo_id="repo-1",
            section_ids=["overview", "summary"],
            checkpoint_data={"current_section": "overview"},
        )
        initial_progress = dict(created.progress)
        updated = manager.update_task_progress(
            task_type="doc_generation",
            repo_id="repo-1",
            section_id="overview",
            status="done",
            checkpoint={"current_section": "summary"},
        )
        resumed = manager.resume_task_memory("doc_generation", "repo-1")

        self.assertEqual(initial_progress, {"overview": "pending", "summary": "pending"})
        self.assertEqual(updated.generated_sections, ["overview"])
        self.assertEqual(updated.checkpoint_data["current_section"], "summary")
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.progress["overview"], "done")
        self.assertEqual(resumed.status, "in_progress")

    def test_task_memory_marks_section_failed_after_fourth_retry(self) -> None:
        manager = MemoryManager()
        manager.create_task_memory(
            task_type="doc_generation",
            repo_id="repo-2",
            section_ids=["architecture"],
        )

        for _ in range(4):
            task_memory = manager.increment_task_retry("doc_generation", "repo-2", "architecture")

        self.assertEqual(task_memory.retry_count["architecture"], 4)
        self.assertEqual(task_memory.progress["architecture"], "failed")
        self.assertEqual(task_memory.status, "failed")


if __name__ == "__main__":
    unittest.main()
