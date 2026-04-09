"""Anchor resolver tests."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol
from app.services.memory.memory_manager import AnchorMemory, FocusMemory, RetrievalMemory
from app.services.retrieval.anchor_resolver import AnchorResolver


class _ResolverRepoStub:
    module = Module(id="M_demo", name="demo", path="demo", summary="", metadata={})
    file_obj = File(
        id="F_demo_service",
        name="service.py",
        path="demo/service.py",
        module_id="M_demo",
        summary="",
        language="python",
        start_line=1,
        end_line=40,
    )
    symbol = Symbol(
        id="S_demo.Service.run",
        name="run",
        qualified_name="Service.run",
        type="method",
        signature="run(self)",
        file_id="F_demo_service",
        module_id="M_demo",
        summary="",
        start_line=10,
        end_line=20,
        visibility="public",
        doc="",
    )
    duplicate_symbol = Symbol(
        id="S_demo.Other.run",
        name="run",
        qualified_name="Other.run",
        type="method",
        signature="run(self)",
        file_id="F_demo_service",
        module_id="M_demo",
        summary="",
        start_line=22,
        end_line=28,
        visibility="public",
        doc="",
    )

    def find_span(self, file_path: str, line_start: int, line_end: int):  # noqa: ANN001
        return []

    def get_symbol_by_id(self, symbol_id: str):
        if symbol_id == self.symbol.id:
            return self.symbol
        if symbol_id == self.duplicate_symbol.id:
            return self.duplicate_symbol
        return None

    def get_file_by_id(self, file_id: str):
        return self.file_obj if file_id == self.file_obj.id else None

    def get_module_by_id(self, module_id: str):
        return self.module if module_id == self.module.id else None

    def find_symbols_by_name(self, name: str, limit: int = 10):  # noqa: ARG002
        if name == "service.run":
            return [self.symbol]
        if name == "run":
            return [self.symbol, self.duplicate_symbol]
        return []

    def find_files_by_name(self, name: str, limit: int = 10):  # noqa: ARG002
        if name == "service.py":
            return [self.file_obj]
        return []

    def find_modules_by_name(self, name: str, limit: int = 10):  # noqa: ARG002
        if name == "demo":
            return [self.module]
        return []


class AnchorResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = _ResolverRepoStub()
        self.resolver = AnchorResolver(self.repository)

    def test_resolve_anchor_prefers_unique_name_match(self) -> None:
        anchor = self.resolver.resolve_anchor(
            question="请解释 `Service.run` 的实现",
            selection=None,
            memory=AnchorMemory(),
        )

        self.assertEqual(anchor.level, "symbol")
        self.assertEqual(anchor.source, "name_match")
        self.assertEqual(anchor.symbol_id, "S_demo.Service.run")
        self.assertEqual(anchor.confidence, 0.85)

    def test_resolve_anchor_uses_ambiguous_name_match_for_small_candidate_set(self) -> None:
        anchor = self.resolver.resolve_anchor(
            question="run 做了什么？",
            selection=None,
            memory=AnchorMemory(),
        )

        self.assertEqual(anchor.level, "symbol")
        self.assertEqual(anchor.source, "name_match")
        self.assertEqual(anchor.confidence, 0.65)

    def test_resolve_anchor_inherits_follow_up_without_new_name(self) -> None:
        memory = AnchorMemory(
            current_anchor=Anchor(
                level="symbol",
                source="explicit_span",
                confidence=0.8,
                module_id="M_demo",
                file_id="F_demo_service",
                symbol_id="S_demo.Service.run",
            ),
            retrieval_memory=RetrievalMemory(),
            focus_memory=FocusMemory(current_focus="service run implementation"),
        )

        anchor = self.resolver.resolve_anchor(
            question="它为什么这样设计？",
            selection=None,
            memory=memory,
        )

        self.assertEqual(anchor.source, "memory_inherit")
        self.assertEqual(anchor.symbol_id, "S_demo.Service.run")
        self.assertEqual(anchor.confidence, 0.72)

    def test_resolve_anchor_does_not_inherit_when_new_name_appears(self) -> None:
        memory = AnchorMemory(
            current_anchor=Anchor(level="file", source="explicit_file", confidence=0.7, file_id="F_demo_service"),
            focus_memory=FocusMemory(current_focus="service implementation"),
        )

        anchor = self.resolver.resolve_anchor(
            question="demo 模块负责什么？",
            selection=None,
            memory=memory,
        )

        self.assertEqual(anchor.source, "name_match")
        self.assertEqual(anchor.level, "module")


if __name__ == "__main__":
    unittest.main()
