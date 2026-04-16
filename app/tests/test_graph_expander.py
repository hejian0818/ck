"""Tests for the GraphExpander module."""

from __future__ import annotations

import unittest

from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.retrieval.graph_expander import GraphExpander


class _GraphRepoStub:
    """Minimal graph repository stub for expansion tests."""

    module = Module(id="M_core", name="core", path="core", metadata={})
    file_obj = File(
        id="F_core_main",
        name="main.py",
        path="core/main.py",
        module_id="M_core",
        language="python",
        start_line=1,
        end_line=50,
    )
    sym_a = Symbol(
        id="S_a",
        name="func_a",
        qualified_name="core.func_a",
        type="function",
        signature="func_a()",
        file_id="F_core_main",
        module_id="M_core",
        start_line=1,
        end_line=5,
        visibility="public",
        doc="",
    )
    sym_b = Symbol(
        id="S_b",
        name="func_b",
        qualified_name="core.func_b",
        type="function",
        signature="func_b()",
        file_id="F_core_main",
        module_id="M_core",
        start_line=7,
        end_line=12,
        visibility="public",
        doc="",
    )
    sym_c = Symbol(
        id="S_c",
        name="func_c",
        qualified_name="core.func_c",
        type="function",
        signature="func_c()",
        file_id="F_core_main",
        module_id="M_core",
        start_line=14,
        end_line=20,
        visibility="public",
        doc="",
    )

    relations = [
        Relation(
            id="R_a_calls_b",
            relation_type="calls",
            source_id="S_a",
            target_id="S_b",
            source_type="symbol",
            target_type="symbol",
            source_module_id="M_core",
            target_module_id="M_core",
        ),
        Relation(
            id="R_b_calls_c",
            relation_type="calls",
            source_id="S_b",
            target_id="S_c",
            source_type="symbol",
            target_type="symbol",
            source_module_id="M_core",
            target_module_id="M_core",
        ),
    ]

    def get_symbol_by_id(self, symbol_id: str):
        for sym in (self.sym_a, self.sym_b, self.sym_c):
            if sym.id == symbol_id:
                return sym
        return None

    def get_file_by_id(self, file_id: str):
        return self.file_obj if file_id == self.file_obj.id else None

    def get_module_by_id(self, module_id: str):
        return self.module if module_id == self.module.id else None

    def get_relations_by_source(self, source_id: str):
        return [r for r in self.relations if r.source_id == source_id]

    def get_relations_by_target(self, target_id: str):
        return [r for r in self.relations if r.target_id == target_id]


class GraphExpanderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _GraphRepoStub()
        self.expander = GraphExpander(self.repo)

    def test_expand_one_hop_finds_callees(self) -> None:
        related, relations, expanded_ids, distances = self.expander.expand(
            question="func_a 调用了谁？",
            current_object=self.repo.sym_a,
            related_objects=[],
            relations=[self.repo.relations[0]],
            max_depth=1,
        )
        related_ids = {o.id for o in related}
        self.assertIn("S_b", related_ids)
        self.assertIn("S_b", expanded_ids)

    def test_expand_two_hops_follows_chain(self) -> None:
        related, relations, expanded_ids, distances = self.expander.expand(
            question="func_a 的调用链",
            current_object=self.repo.sym_a,
            related_objects=[],
            relations=[self.repo.relations[0]],
            max_depth=2,
        )
        related_ids = {o.id for o in related}
        self.assertIn("S_b", related_ids)
        # S_c may or may not be included depending on gain threshold

    def test_expand_includes_containers(self) -> None:
        related, _, _, _ = self.expander.expand(
            question="func_a callees",
            current_object=self.repo.sym_a,
            related_objects=[],
            relations=[self.repo.relations[0]],
            max_depth=1,
        )
        related_ids = {o.id for o in related}
        # File and module containers should be attached for expanded symbols
        self.assertIn("F_core_main", related_ids)
        self.assertIn("M_core", related_ids)

    def test_expand_returns_graph_distances(self) -> None:
        _, _, _, distances = self.expander.expand(
            question="func_a 调用关系",
            current_object=self.repo.sym_a,
            related_objects=[],
            relations=[self.repo.relations[0]],
            max_depth=1,
        )
        self.assertIn("S_b", distances)
        self.assertEqual(distances["S_b"], 1)

    def test_expand_excludes_current_object_from_related(self) -> None:
        related, _, _, _ = self.expander.expand(
            question="query",
            current_object=self.repo.sym_a,
            related_objects=[self.repo.sym_a],
            relations=[self.repo.relations[0]],
            max_depth=1,
        )
        related_ids = {o.id for o in related}
        self.assertNotIn("S_a", related_ids)

    def test_expand_none_anchor_returns_empty(self) -> None:
        # No symbols to seed, so expansion is a no-op
        related, relations, expanded_ids, distances = self.expander.expand(
            question="general query",
            current_object=None,
            related_objects=[],
            relations=[],
            max_depth=1,
        )
        self.assertEqual(len(expanded_ids), 0)

    def test_allowed_expansions_detects_caller_hint(self) -> None:
        modes = GraphExpander._allowed_expansions("谁调用了这个方法？")
        self.assertIn("callers", modes)

    def test_allowed_expansions_defaults_to_all(self) -> None:
        modes = GraphExpander._allowed_expansions("explain this function")
        self.assertIn("callers", modes)
        self.assertIn("callees", modes)
        self.assertIn("depends_on", modes)


if __name__ == "__main__":
    unittest.main()
