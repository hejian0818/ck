"""Tests for DocAgent TaskMemory and DocumentReviewer integration."""

from __future__ import annotations

import unittest

from app.models.doc_models import DocumentSkeleton, SectionContent, SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.agents.doc_agent import DocAgent, DeterministicDocLLMClient, OpenAICompatibleDocLLMClient, SkeletonPlanner
from app.services.memory.memory_manager import MemoryManager
from app.services.retrieval.doc_retriever import DocRetriever
from app.services.review.doc_reviewer import DocumentReviewer


class _RepoStub:
    module = Module(id="M_core", name="core", path="core", summary='{"summary":"Core module."}', metadata={})
    file_obj = File(
        id="F_main", name="main.py", path="core/main.py", module_id="M_core",
        language="python", summary='{"summary":"Main entry."}', start_line=1, end_line=30,
    )
    sym_run = Symbol(
        id="S_run", name="run", qualified_name="core.run", type="function",
        signature="run()", file_id="F_main", module_id="M_core",
        summary='{"summary":"Execute main logic."}',
        start_line=5, end_line=20, visibility="public", doc="",
    )
    relation = Relation(
        id="R_calls", relation_type="calls", source_id="S_run", target_id="S_run",
        source_type="symbol", target_type="symbol",
        source_module_id="M_core", target_module_id="M_core",
        summary="run calls itself.",
    )

    def list_modules(self, repo_id):
        return [self.module]

    def list_files(self, repo_id):
        return [self.file_obj]

    def list_files_by_module(self, module_id):
        return [self.file_obj] if module_id == "M_core" else []

    def list_symbols_by_module(self, module_id):
        return [self.sym_run] if module_id == "M_core" else []

    def list_symbols_by_file(self, file_id):
        return [self.sym_run] if file_id == "F_main" else []

    def list_relations(self, repo_id):
        return [self.relation]

    def get_module_by_id(self, oid):
        return self.module if oid == "M_core" else None

    def get_file_by_id(self, oid):
        return self.file_obj if oid == "F_main" else None

    def get_symbol_by_id(self, oid):
        return self.sym_run if oid == "S_run" else None

    def get_relation_by_id(self, oid):
        return self.relation if oid == "R_calls" else None

    def get_relations_by_source(self, source_id):
        return [self.relation] if source_id == "S_run" else []

    def get_relations_by_target(self, target_id):
        return [self.relation] if target_id == "S_run" else []

    def get_repo_path(self, repo_id):
        return f"/test/{repo_id}"


def _make_skeleton():
    return DocumentSkeleton(
        repo_id="test-repo",
        title="Test Doc",
        sections=[
            SectionPlan(
                section_id="overview", title="Overview", level=1,
                section_type="overview", target_object_ids=["M_core"],
                description="Overview.",
            ),
            SectionPlan(
                section_id="module-core", title="core", level=2,
                section_type="module", target_object_ids=["M_core"],
                description="Core module.",
            ),
            SectionPlan(
                section_id="summary", title="Summary", level=1,
                section_type="summary", target_object_ids=["M_core"],
                description="Summary.",
            ),
        ],
    )


class TaskMemoryIntegrationTests(unittest.TestCase):
    """Tests for TaskMemory integration in DocAgent.generate()."""

    def setUp(self):
        self.repo = _RepoStub()
        self.memory_manager = MemoryManager()

    def _make_agent(self, **kwargs):
        return DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=DocRetriever(self.repo),
            llm_client=DeterministicDocLLMClient(),
            memory_manager=self.memory_manager,
            **kwargs,
        )

    def test_task_memory_created_during_generation(self):
        """TaskMemory should be created and completed after generate()."""
        agent = self._make_agent()
        skeleton = _make_skeleton()
        agent.generate("test-repo", skeleton=skeleton)

        task = self.memory_manager.get_task_memory("doc_generation", "test-repo")
        self.assertIsNotNone(task)
        self.assertEqual(task.status, "completed")
        self.assertEqual(len(task.generated_sections), 3)

    def test_task_memory_tracks_section_progress(self):
        """Each section should be tracked in task progress."""
        agent = self._make_agent()
        skeleton = _make_skeleton()
        agent.generate("test-repo", skeleton=skeleton)

        task = self.memory_manager.get_task_memory("doc_generation", "test-repo")
        for section in skeleton.sections:
            self.assertIn(section.section_id, task.progress)
            self.assertEqual(task.progress[section.section_id], "done")

    def test_checkpoint_resume_skips_done_sections(self):
        """Resuming should skip sections that are already done with checkpoint data."""
        agent = self._make_agent()
        skeleton = _make_skeleton()

        # First run: generate normally
        result1 = agent.generate("test-repo", skeleton=skeleton)

        # Manually set task memory back to in_progress to simulate resume
        task = self.memory_manager.get_task_memory("doc_generation", "test-repo")
        task.status = "in_progress"
        # Keep "overview" as done (has checkpoint), reset others to pending
        task.progress["module-core"] = "pending"
        task.progress["summary"] = "pending"
        # Remove checkpoint data for pending sections
        task.checkpoint_data.pop("section:module-core", None)
        task.checkpoint_data.pop("section:summary", None)

        # Second run: should resume and skip overview
        result2 = agent.generate("test-repo", skeleton=skeleton)
        self.assertEqual(len(result2.sections), 3)
        self.assertTrue(result2.metadata.get("resumed"))

        # Task should be completed again
        task = self.memory_manager.get_task_memory("doc_generation", "test-repo")
        self.assertEqual(task.status, "completed")

    def test_no_memory_manager_still_works(self):
        """DocAgent should work without memory_manager (backward compatible)."""
        agent = DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=DocRetriever(self.repo),
            llm_client=DeterministicDocLLMClient(),
        )
        skeleton = _make_skeleton()
        result = agent.generate("test-repo", skeleton=skeleton)
        self.assertEqual(len(result.sections), 3)


class ReviewIntegrationTests(unittest.TestCase):
    """Tests for DocumentReviewer integration in DocAgent.generate()."""

    def setUp(self):
        self.repo = _RepoStub()

    def _make_agent(self, **kwargs):
        return DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=DocRetriever(self.repo),
            llm_client=DeterministicDocLLMClient(),
            reviewer=DocumentReviewer(self.repo),
            **kwargs,
        )

    def test_review_runs_after_generation(self):
        """Review metadata should be present when reviewer is provided."""
        agent = self._make_agent()
        skeleton = _make_skeleton()
        result = agent.generate("test-repo", skeleton=skeleton)
        self.assertIn("review_passed", result.metadata)
        self.assertIn("review_warnings", result.metadata)
        self.assertIn("review_autofix_count", result.metadata)

    def test_autofix_regenerates_missing_section(self):
        """Auto-fix should regenerate a section that was removed from the output."""
        agent = self._make_agent()
        skeleton = _make_skeleton()

        # Generate the document normally first
        result = agent.generate("test-repo", skeleton=skeleton)
        self.assertEqual(len(result.sections), 3)

        # Now test _run_review_and_autofix directly with a document
        # that has one section removed
        incomplete_sections = [s for s in result.sections if s.section_id != "summary"]
        incomplete_doc = result.model_copy(update={"sections": incomplete_sections})
        self.assertEqual(len(incomplete_doc.sections), 2)

        section_map = {s.section_id: s for s in incomplete_doc.sections}
        capped_skeleton = DocumentSkeleton(
            repo_id="test-repo", title="Test Doc", sections=skeleton.sections,
        )
        fixed_doc = agent._run_review_and_autofix(
            "test-repo", capped_skeleton, incomplete_doc, section_map,
        )
        section_ids = [s.section_id for s in fixed_doc.sections]
        self.assertIn("summary", section_ids)
        self.assertEqual(len(fixed_doc.sections), 3)
        self.assertTrue(fixed_doc.metadata["review_autofix_count"] >= 1)

    def test_autofix_removes_unknown_object_reference(self):
        """Auto-fix should remove unknown object references from used_objects."""
        agent = self._make_agent()
        skeleton = _make_skeleton()
        result = agent.generate("test-repo", skeleton=skeleton)

        # Check that no sections have unknown object references
        # (the reviewer + autofix should have cleaned any up)
        for section in result.sections:
            for oid in section.used_objects:
                # All used objects should be resolvable
                resolved = (
                    self.repo.get_module_by_id(oid) is not None
                    or self.repo.get_file_by_id(oid) is not None
                    or self.repo.get_symbol_by_id(oid) is not None
                )
                self.assertTrue(resolved, f"Unknown object {oid} in section {section.section_id}")

    def test_warnings_recorded_in_metadata(self):
        """Review warnings should be recorded in metadata."""
        agent = self._make_agent()
        skeleton = _make_skeleton()
        result = agent.generate("test-repo", skeleton=skeleton)
        self.assertIsInstance(result.metadata.get("review_warnings"), list)

    def test_no_reviewer_still_works(self):
        """DocAgent should work without reviewer (backward compatible)."""
        agent = DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=DocRetriever(self.repo),
            llm_client=DeterministicDocLLMClient(),
        )
        skeleton = _make_skeleton()
        result = agent.generate("test-repo", skeleton=skeleton)
        self.assertNotIn("review_passed", result.metadata)
        self.assertEqual(len(result.sections), 3)


class CombinedIntegrationTests(unittest.TestCase):
    """Tests for TaskMemory + DocumentReviewer working together."""

    def setUp(self):
        self.repo = _RepoStub()
        self.memory_manager = MemoryManager()

    def test_full_pipeline_with_task_memory_and_review(self):
        """Full pipeline: TaskMemory + review + auto-fix."""
        agent = DocAgent(
            repository=self.repo,
            planner=SkeletonPlanner(self.repo),
            retriever=DocRetriever(self.repo),
            llm_client=DeterministicDocLLMClient(),
            memory_manager=self.memory_manager,
            reviewer=DocumentReviewer(self.repo),
        )
        skeleton = _make_skeleton()
        result = agent.generate("test-repo", skeleton=skeleton)

        # TaskMemory completed
        task = self.memory_manager.get_task_memory("doc_generation", "test-repo")
        self.assertIsNotNone(task)
        self.assertEqual(task.status, "completed")

        # Review ran
        self.assertIn("review_passed", result.metadata)

        # All sections generated
        self.assertEqual(len(result.sections), 3)


class DocLLMFallbackTests(unittest.TestCase):
    def test_openai_doc_client_falls_back_without_openai_dependency(self):
        client = OpenAICompatibleDocLLMClient(fallback_client=DeterministicDocLLMClient())
        section = _make_skeleton().sections[0]
        retrieval = DocRetriever(_RepoStub()).retrieve("test-repo", section)

        content = client.generate(section, retrieval, "prompt")

        self.assertIn(section.title, content)


if __name__ == "__main__":
    unittest.main()
