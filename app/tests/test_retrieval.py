"""Retriever tests."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Relation, Symbol
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


if __name__ == "__main__":
    unittest.main()
