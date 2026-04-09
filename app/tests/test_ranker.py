"""Tests for the Ranker module."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol
from app.services.retrieval.ranker import Ranker


def _make_symbol(id_: str, name: str, file_id: str = "F_1", module_id: str = "M_1") -> Symbol:
    return Symbol(
        id=id_,
        name=name,
        qualified_name=f"Cls.{name}",
        type="method",
        signature=f"{name}(self)",
        file_id=file_id,
        module_id=module_id,
        start_line=1,
        end_line=5,
        visibility="public",
        doc="",
    )


def _make_file(id_: str = "F_1", name: str = "service.py", module_id: str = "M_1") -> File:
    return File(
        id=id_,
        name=name,
        path=f"app/{name}",
        module_id=module_id,
        language="python",
        start_line=1,
        end_line=50,
    )


def _make_module(id_: str = "M_1", name: str = "app") -> Module:
    return Module(id=id_, name=name, path=name, metadata={})


class RankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ranker = Ranker()
        self.anchor = Anchor(
            level="symbol",
            source="name_match",
            confidence=0.85,
            module_id="M_1",
            file_id="F_1",
            symbol_id="S_target",
        )

    def test_rank_returns_ordered_list_and_scores(self) -> None:
        candidates = [
            _make_symbol("S_target", "run"),
            _make_symbol("S_helper", "helper"),
            _make_file(),
        ]
        ordered, scores = self.ranker.rank(
            anchor=self.anchor,
            question="explain run method",
            current_object=_make_symbol("S_target", "run"),
            candidates=candidates,
        )
        self.assertIsInstance(ordered, list)
        self.assertIsInstance(scores, dict)
        self.assertTrue(all(score > 0 for score in scores.values()))

    def test_rank_prefers_anchor_match(self) -> None:
        target = _make_symbol("S_target", "run")
        other = _make_symbol("S_other", "other", file_id="F_2", module_id="M_2")
        ordered, scores = self.ranker.rank(
            anchor=self.anchor,
            question="explain run",
            current_object=None,
            candidates=[target, other],
        )
        self.assertEqual(ordered[0].id, "S_target")
        self.assertGreater(scores["S_target"], scores["S_other"])

    def test_rank_uses_name_hit(self) -> None:
        named = _make_symbol("S_1", "calculate_total")
        unnamed = _make_symbol("S_2", "xyz_helper")
        anchor = Anchor(level="none", source="none", confidence=0.0)
        ordered, scores = self.ranker.rank(
            anchor=anchor,
            question="how does calculate_total work?",
            current_object=None,
            candidates=[named, unnamed],
        )
        self.assertEqual(ordered[0].id, "S_1")

    def test_rank_uses_vector_scores(self) -> None:
        s1 = _make_symbol("S_1", "alpha")
        s2 = _make_symbol("S_2", "beta")
        anchor = Anchor(level="none", source="none", confidence=0.0)
        ordered, scores = self.ranker.rank(
            anchor=anchor,
            question="query",
            current_object=None,
            candidates=[s1, s2],
            vector_scores={"S_2": 0.95},
        )
        self.assertEqual(ordered[0].id, "S_2")

    def test_rank_uses_memory_weight(self) -> None:
        s1 = _make_symbol("S_1", "alpha")
        s2 = _make_symbol("S_2", "beta")
        anchor = Anchor(level="none", source="none", confidence=0.0)
        _, scores_with_mem = self.ranker.rank(
            anchor=anchor,
            question="query",
            current_object=None,
            candidates=[s1, s2],
            memory_object_ids=["S_1"],
        )
        _, scores_without_mem = self.ranker.rank(
            anchor=anchor,
            question="query",
            current_object=None,
            candidates=[s1, s2],
        )
        self.assertGreater(scores_with_mem["S_1"], scores_without_mem["S_1"])

    def test_rank_uses_graph_distance(self) -> None:
        s1 = _make_symbol("S_1", "close")
        s2 = _make_symbol("S_2", "far")
        anchor = Anchor(level="none", source="none", confidence=0.0)
        ordered, _ = self.ranker.rank(
            anchor=anchor,
            question="query",
            current_object=None,
            candidates=[s1, s2],
            graph_distances={"S_1": 1, "S_2": 3},
        )
        self.assertEqual(ordered[0].id, "S_1")

    def test_rank_respects_top_k(self) -> None:
        candidates = [_make_symbol(f"S_{i}", f"sym_{i}") for i in range(10)]
        anchor = Anchor(level="none", source="none", confidence=0.0)
        ordered, _ = self.ranker.rank(
            anchor=anchor,
            question="query",
            current_object=None,
            candidates=candidates,
            top_k=3,
        )
        self.assertLessEqual(len(ordered), 3)

    def test_current_object_excluded_from_related(self) -> None:
        current = _make_symbol("S_current", "main")
        other = _make_symbol("S_other", "helper")
        ordered, scores = self.ranker.rank(
            anchor=self.anchor,
            question="query",
            current_object=current,
            candidates=[current, other],
        )
        self.assertNotIn("S_current", [o.id for o in ordered])
        self.assertEqual(scores.get("S_current"), 1.0)


if __name__ == "__main__":
    unittest.main()
