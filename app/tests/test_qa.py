"""QA agent tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.graph_objects import File, Module, Relation, Span, Symbol
from app.models.qa_models import CodeSelection
from app.services.agents.qa_agent import QAAgent
from app.services.memory.memory_manager import MemoryManager
from app.services.retrieval.retriever import Retriever


class _RepoStub:
    module = Module(id="M_app_core", name="app_core", path="app_core", metadata={})
    file_obj = File(
        id="F_services",
        name="services.py",
        path="data/test_repo/app_core/services.py",
        module_id="M_app_core",
        language="python",
        start_line=1,
        end_line=10,
    )
    greet = Symbol(
        id="S_app_core.GreetingService.greet",
        name="greet",
        qualified_name="GreetingService.greet",
        type="method",
        signature="greet(self, name)",
        file_id="F_services",
        module_id="M_app_core",
        start_line=6,
        end_line=7,
        visibility="public",
        doc="",
    )
    build_message = Symbol(
        id="S_app_core.build_message",
        name="build_message",
        qualified_name="build_message",
        type="function",
        signature="build_message(name)",
        file_id="F_utils",
        module_id="M_app_core",
        start_line=7,
        end_line=8,
        visibility="public",
        doc="",
    )

    def find_span(self, file_path: str, line_start: int, line_end: int):
        _ = (file_path, line_start, line_end)
        return [
            Span(
                file_path="data/test_repo/app_core/services.py",
                line_start=6,
                line_end=7,
                module_id="M_app_core",
                file_id="F_services",
                symbol_id="S_app_core.GreetingService.greet",
                node_type="symbol",
            )
        ]

    def get_symbol_by_id(self, symbol_id: str):
        if symbol_id == self.greet.id:
            return self.greet
        if symbol_id == self.build_message.id:
            return self.build_message
        return None

    def get_file_by_id(self, file_id: str):
        return self.file_obj if file_id == self.file_obj.id else None

    def get_module_by_id(self, module_id: str):
        return self.module if module_id == self.module.id else None

    def get_relations_by_source(self, source_id: str):
        if source_id != self.greet.id:
            return []
        return [
            Relation(
                id="R_1",
                relation_type="calls",
                source_id=self.greet.id,
                target_id=self.build_message.id,
                source_type="symbol",
                target_type="symbol",
                source_module_id="M_app_core",
                target_module_id="M_app_core",
            )
        ]

    def get_relations_by_target(self, target_id: str):
        return []

    def list_symbols_by_file(self, file_id: str):
        return [self.greet]

    def list_files_by_module(self, module_id: str):
        return [self.file_obj]

    def find_symbols_by_name(self, name: str, limit: int = 10):  # noqa: ARG002
        if name in {"greetingservice.greet", "greet"}:
            return [self.greet]
        return []

    def find_files_by_name(self, name: str, limit: int = 10):  # noqa: ARG002
        if name == "services.py":
            return [self.file_obj]
        return []

    def find_modules_by_name(self, name: str, limit: int = 10):  # noqa: ARG002
        if name == "app_core":
            return [self.module]
        return []

    def get_relation_by_id(self, relation_id: str):
        if relation_id == "R_1":
            return self.get_relations_by_source(self.greet.id)[0]
        return None


class _LLMStub:
    def generate(self, prompt: str) -> str:
        return f"stubbed answer for: {prompt.splitlines()[0]}"


class _EmbeddingBuilderStub:
    def encode_summary(self, summary: str) -> list[float]:
        return [0.1, 0.9]


class _VectorStoreStub:
    def search_symbols(self, repo_id: str, query_vector: list[float]):
        _ = (repo_id, query_vector)
        return [SimpleNamespace(object_id="S_app_core.GreetingService.greet", object_type="symbol", similarity=0.92)]

    def search_files(self, repo_id: str, query_vector: list[float]):
        _ = (repo_id, query_vector)
        return []

    def search_modules(self, repo_id: str, query_vector: list[float]):
        _ = (repo_id, query_vector)
        return []


class QAAgentTests(unittest.TestCase):
    def test_answer_returns_anchor_and_used_objects(self) -> None:
        agent = QAAgent(
            repository=_RepoStub(),
            memory_manager=MemoryManager(),
            llm_client=_LLMStub(),
            retriever=Retriever(_RepoStub()),
        )
        response = agent.answer(
            repo_id="repo_sample",
            question="这个方法做什么？",
            selection=CodeSelection(
                file_path="data/test_repo/app_core/services.py",
                line_start=6,
                line_end=7,
            ),
            session_id="session-1",
        )
        self.assertEqual(response.anchor.level, "symbol")
        self.assertIn("S_app_core.GreetingService.greet", response.used_objects)
        self.assertFalse(response.need_more_context)
        self.assertEqual(response.strategy_used, "S1")
        self.assertFalse(response.degraded)
        self.assertGreaterEqual(response.metrics.A, 0.8)

    def test_answer_degrades_without_anchor_and_inherits_memory_on_follow_up(self) -> None:
        memory_manager = MemoryManager()
        agent = QAAgent(
            repository=_RepoStub(),
            memory_manager=memory_manager,
            llm_client=_LLMStub(),
            retriever=Retriever(_RepoStub()),
        )

        first_response = agent.answer(
            repo_id="repo_sample",
            question="这个方法做什么？",
            selection=CodeSelection(
                file_path="data/test_repo/app_core/services.py",
                line_start=6,
                line_end=7,
            ),
            session_id="session-2",
        )
        follow_up_response = agent.answer(
            repo_id="repo_sample",
            question="它会调用谁？",
            selection=None,
            session_id="session-2",
        )
        degraded_response = agent.answer(
            repo_id="repo_sample",
            question="帮我分析一下",
            selection=None,
            session_id="session-3",
        )

        self.assertEqual(first_response.anchor.level, "symbol")
        self.assertEqual(follow_up_response.anchor.source, "memory_inherit")
        self.assertFalse(follow_up_response.degraded)
        self.assertTrue(degraded_response.degraded)
        self.assertEqual(degraded_response.strategy_used, "S4")
        self.assertTrue(degraded_response.need_more_context)
        self.assertTrue(degraded_response.suggestions)

    def test_answer_supports_name_based_anchor_without_selection(self) -> None:
        repository = _RepoStub()
        agent = QAAgent(
            repository=repository,
            memory_manager=MemoryManager(),
            llm_client=_LLMStub(),
            retriever=Retriever(
                repository,
                embedding_builder=_EmbeddingBuilderStub(),
                vector_store=_VectorStoreStub(),
            ),
        )

        response = agent.answer(
            repo_id="repo_sample",
            question="GreetingService.greet 做什么？",
            selection=None,
            session_id="session-4",
        )

        self.assertEqual(response.anchor.source, "name_match")
        self.assertFalse(response.degraded)
        self.assertIn("S_app_core.GreetingService.greet", response.used_objects)


if __name__ == "__main__":
    unittest.main()
