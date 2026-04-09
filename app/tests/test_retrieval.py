"""Retriever tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.memory.memory_manager import AnchorMemory, RetrievalMemory
from app.services.retrieval.retriever import Retriever


class _RepoStub:
    module = Module(id="M_app_core", name="app_core", path="app_core", metadata={})
    file_obj = File(
        id="F_services",
        name="services.py",
        path="app_core/services.py",
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
    helper = Symbol(
        id="S_app_core.helper",
        name="helper",
        qualified_name="helper",
        type="function",
        signature="helper()",
        file_id="F_services",
        module_id="M_app_core",
        start_line=8,
        end_line=9,
        visibility="public",
        doc="",
    )

    def get_symbol_by_id(self, symbol_id: str):
        if symbol_id == self.greet.id:
            return self.greet
        if symbol_id == self.build_message.id:
            return self.build_message
        if symbol_id == self.helper.id:
            return self.helper
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
        if target_id != self.build_message.id:
            return []
        return [
            Relation(
                id="R_2",
                relation_type="calls",
                source_id=self.helper.id,
                target_id=self.build_message.id,
                source_type="symbol",
                target_type="symbol",
                source_module_id="M_app_core",
                target_module_id="M_app_core",
            )
        ]

    def list_symbols_by_file(self, file_id: str):
        return [self.greet, self.helper]

    def list_files_by_module(self, module_id: str):
        return [self.file_obj]

    def get_relation_by_id(self, relation_id: str):
        for relation in self.get_relations_by_source(self.greet.id) + self.get_relations_by_target(
            self.build_message.id
        ):
            if relation.id == relation_id:
                return relation
        return None


class _EmbeddingBuilderStub:
    def encode_summary(self, summary: str) -> list[float]:
        self.last_summary = summary
        return [0.1, 0.9]


class _VectorStoreStub:
    def search_symbols(self, repo_id: str, query_vector: list[float]):
        _ = (repo_id, query_vector)
        return [
            SimpleNamespace(object_id="S_app_core.helper", object_type="symbol", similarity=0.89),
        ]

    def search_files(self, repo_id: str, query_vector: list[float]):
        _ = (repo_id, query_vector)
        return [
            SimpleNamespace(object_id="F_services", object_type="file", similarity=0.72),
        ]

    def search_modules(self, repo_id: str, query_vector: list[float]):
        _ = (repo_id, query_vector)
        return [
            SimpleNamespace(object_id="M_app_core", object_type="module", similarity=0.61),
        ]


class RetrieverTests(unittest.TestCase):
    def test_symbol_anchor_retrieves_direct_neighbors(self) -> None:
        result = Retriever(_RepoStub()).retrieve(
            anchor=Anchor(
                level="symbol",
                source="explicit_span",
                confidence=0.8,
                module_id="M_app_core",
                file_id="F_services",
                symbol_id="S_app_core.GreetingService.greet",
            ),
            question="谁调用了这个方法？",
        )
        self.assertEqual(result.current_object.id, "S_app_core.GreetingService.greet")
        self.assertIn("S_app_core.build_message", [obj.id for obj in result.related_objects])

    def test_retrieve_merges_vector_hits_and_memory_weight(self) -> None:
        retriever = Retriever(
            _RepoStub(),
            embedding_builder=_EmbeddingBuilderStub(),
            vector_store=_VectorStoreStub(),
        )

        result = retriever.retrieve(
            anchor=Anchor(
                level="file",
                source="explicit_file",
                confidence=0.8,
                module_id="M_app_core",
                file_id="F_services",
            ),
            question="这个文件里哪个函数负责辅助逻辑？",
            repo_id="repo_sample",
            memory=AnchorMemory(
                retrieval_memory=RetrievalMemory(recent_object_ids=["S_app_core.helper"]),
            ),
        )

        self.assertIn("S_app_core.helper", [obj.id for obj in result.related_objects])
        self.assertGreater(result.object_scores["S_app_core.helper"], 0.5)

    def test_expand_retrieval_follows_supported_graph_relations(self) -> None:
        retriever = Retriever(_RepoStub())
        initial = retriever.retrieve(
            anchor=Anchor(
                level="symbol",
                source="explicit_span",
                confidence=0.8,
                module_id="M_app_core",
                file_id="F_services",
                symbol_id="S_app_core.GreetingService.greet",
            ),
            question="它调用了谁？",
        )

        expanded = retriever.expand_retrieval(
            initial,
            question="谁调用了 build_message？",
            memory=AnchorMemory(),
            max_depth=2,
        )

        self.assertIn("S_app_core.helper", [obj.id for obj in expanded.related_objects])


if __name__ == "__main__":
    unittest.main()
