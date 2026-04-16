"""End-to-end integration tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.graph_objects import File, Module, Relation, Span, Symbol
from app.services.agents.doc_agent import DeterministicDocLLMClient, DocAgent, SkeletonPlanner
from app.services.agents.qa_agent import QAAgent
from app.services.memory.memory_manager import MemoryManager
from app.services.retrieval.doc_retriever import DocRetriever
from app.services.retrieval.retriever import Retriever
from app.services.review.doc_reviewer import DocumentReviewer


class _IntegrationRepoStub:
    """Shared stub repository for integration tests."""

    module = Module(id="M_core", name="core", path="core", summary='{"summary":"Core module."}', metadata={})
    file_obj = File(
        id="F_main", name="main.py", path="core/main.py", module_id="M_core",
        language="python", summary='{"summary":"Main entry point."}', start_line=1, end_line=30,
    )
    sym_run = Symbol(
        id="S_run", name="run", qualified_name="core.run", type="function",
        signature="run()", file_id="F_main", module_id="M_core",
        summary='{"summary":"Execute main logic."}',
        start_line=5, end_line=20, visibility="public", doc="",
    )
    sym_helper = Symbol(
        id="S_helper", name="helper", qualified_name="core.helper", type="function",
        signature="helper()", file_id="F_main", module_id="M_core",
        start_line=22, end_line=28, visibility="public", doc="",
    )
    relation = Relation(
        id="R_calls", relation_type="calls", source_id="S_run", target_id="S_helper",
        source_type="symbol", target_type="symbol",
        source_module_id="M_core", target_module_id="M_core",
        summary="run calls helper.",
    )

    def list_modules(self, repo_id):
        return [self.module]

    def list_files(self, repo_id):
        return [self.file_obj]

    def list_files_by_module(self, module_id):
        return [self.file_obj] if module_id == "M_core" else []

    def list_symbols_by_module(self, module_id):
        return [self.sym_run, self.sym_helper] if module_id == "M_core" else []

    def list_symbols_by_file(self, file_id):
        return [self.sym_run, self.sym_helper] if file_id == "F_main" else []

    def list_relations(self, repo_id):
        return [self.relation]

    def get_module_by_id(self, oid):
        return self.module if oid == "M_core" else None

    def get_file_by_id(self, oid):
        return self.file_obj if oid == "F_main" else None

    def get_symbol_by_id(self, oid):
        return {"S_run": self.sym_run, "S_helper": self.sym_helper}.get(oid)

    def get_relation_by_id(self, oid):
        return self.relation if oid == "R_calls" else None

    def get_relations_by_source(self, source_id):
        return [self.relation] if source_id == "S_run" else []

    def get_relations_by_target(self, target_id):
        return [self.relation] if target_id == "S_helper" else []

    def get_repo_path(self, repo_id):
        return f"/test/{repo_id}"

    def find_span(self, file_path, line_start, line_end):
        if file_path == "core/main.py":
            return [Span(
                file_path=file_path, line_start=5, line_end=20,
                module_id="M_core", file_id="F_main", symbol_id="S_run", node_type="function",
            )]
        return []

    def find_modules_by_name(self, name, limit=10):
        if "core" in name.lower():
            return [self.module]
        return []

    def find_files_by_name(self, name, limit=10):
        if "main" in name.lower():
            return [self.file_obj]
        return []

    def find_symbols_by_name(self, name, limit=10):
        results = []
        if "run" in name.lower():
            results.append(self.sym_run)
        if "helper" in name.lower():
            results.append(self.sym_helper)
        return results


class _LLMStub:
    def generate(self, prompt):
        return "This is a stub LLM response about the code."


class _EmbeddingStub:
    def encode_summary(self, summary):
        return [0.1, 0.9]


class _VectorStoreStub:
    def search_symbols(self, repo_id, query_vector, **kwargs):
        return [SimpleNamespace(object_id="S_run", object_type="symbol", similarity=0.85)]

    def search_files(self, repo_id, query_vector, **kwargs):
        return []

    def search_modules(self, repo_id, query_vector, **kwargs):
        return []

    def search_relations(self, repo_id, query_vector, **kwargs):
        return []


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _IntegrationRepoStub()
        self.repo_id = "test-repo"

    def test_scan_to_doc_pipeline(self) -> None:
        """Plan skeleton -> generate document -> verify all sections present."""
        planner = SkeletonPlanner(self.repo)
        skeleton = planner.plan(self.repo_id)
        self.assertTrue(len(skeleton.sections) > 0)

        retriever = DocRetriever(self.repo)
        agent = DocAgent(
            repository=self.repo,
            planner=planner,
            retriever=retriever,
            llm_client=DeterministicDocLLMClient(),
        )
        document = agent.generate(self.repo_id, skeleton)

        self.assertEqual(len(document.sections), len(skeleton.sections))
        for section in document.sections:
            self.assertTrue(len(section.content) > 0)
            self.assertTrue(section.title)

    def test_doc_review_end_to_end(self) -> None:
        """Generate document then review it for consistency."""
        planner = SkeletonPlanner(self.repo)
        skeleton = planner.plan(self.repo_id)
        retriever = DocRetriever(self.repo)
        agent = DocAgent(
            repository=self.repo,
            planner=planner,
            retriever=retriever,
            llm_client=DeterministicDocLLMClient(),
        )
        document = agent.generate(self.repo_id, skeleton)

        reviewer = DocumentReviewer(self.repo)
        review = reviewer.review(skeleton, document)

        self.assertIsNotNone(review)
        self.assertIsInstance(review.issues, list)
        # All planned sections should be generated
        planned_ids = {s.section_id for s in skeleton.sections}
        generated_ids = {s.section_id for s in document.sections}
        self.assertEqual(planned_ids, generated_ids)

    def test_degraded_qa_returns_suggestions(self) -> None:
        """QA with no anchor returns degraded answer with suggestions."""
        memory_manager = MemoryManager()
        retriever = Retriever(
            self.repo,
            embedding_builder=_EmbeddingStub(),
            vector_store=_VectorStoreStub(),
        )
        agent = QAAgent(
            repository=self.repo,
            memory_manager=memory_manager,
            retriever=retriever,
            llm_client=_LLMStub(),
        )
        response = agent.answer(
            repo_id=self.repo_id,
            question="这段代码做了什么？",
            selection=None,
            session_id="test-session",
        )
        self.assertTrue(response.degraded)
        self.assertTrue(len(response.suggestions) > 0)

    def test_qa_with_name_anchor(self) -> None:
        """QA with a name-based question resolves an anchor."""
        memory_manager = MemoryManager()
        retriever = Retriever(
            self.repo,
            embedding_builder=_EmbeddingStub(),
            vector_store=_VectorStoreStub(),
        )
        agent = QAAgent(
            repository=self.repo,
            memory_manager=memory_manager,
            retriever=retriever,
            llm_client=_LLMStub(),
        )
        response = agent.answer(
            repo_id=self.repo_id,
            question="run 函数的作用是什么？",
            selection=None,
            session_id="test-session-2",
        )
        self.assertIsNotNone(response.anchor)
        self.assertTrue(len(response.answer) > 0)


if __name__ == "__main__":
    unittest.main()
