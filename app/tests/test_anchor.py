"""Anchor resolver tests."""

from __future__ import annotations

import unittest

from app.models.graph_objects import Span, Symbol
from app.models.qa_models import CodeSelection
from app.services.memory.memory_manager import AnchorMemory
from app.services.retrieval.anchor_resolver import AnchorResolver


class _RepoStub:
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
        return Symbol(
            id=symbol_id,
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


class AnchorResolverTests(unittest.TestCase):
    def test_resolve_anchor_prefers_symbol_span(self) -> None:
        resolver = AnchorResolver(_RepoStub())
        anchor = resolver.resolve_anchor(
            question="这个方法做什么？",
            selection=CodeSelection(
                file_path="data/test_repo/app_core/services.py",
                line_start=6,
                line_end=7,
            ),
            memory=AnchorMemory(),
        )
        self.assertEqual(anchor.level, "symbol")
        self.assertEqual(anchor.symbol_id, "S_app_core.GreetingService.greet")


if __name__ == "__main__":
    unittest.main()
