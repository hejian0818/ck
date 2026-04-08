"""Metrics calculation tests."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Relation, Symbol
from app.models.qa_models import RetrievalResult
from app.services.agents.metrics import MetricsCalculator


class MetricsCalculatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calculator = MetricsCalculator()
        self.anchor = Anchor(level="symbol", source="explicit_span", confidence=0.75, symbol_id="S_core.main")
        self.module_core = Module(id="M_core", name="core", path="core", metadata={})
        self.module_utils = Module(id="M_utils", name="utils", path="utils", metadata={})
        self.file_main = File(
            id="F_main",
            name="main.py",
            path="core/main.py",
            module_id="M_core",
            language="python",
            start_line=1,
            end_line=20,
        )
        self.file_helpers = File(
            id="F_helpers",
            name="helpers.py",
            path="utils/helpers.py",
            module_id="M_utils",
            language="python",
            start_line=1,
            end_line=20,
        )
        self.symbol_main = Symbol(
            id="S_core.main",
            name="main",
            qualified_name="main",
            type="function",
            signature="main()",
            file_id="F_main",
            module_id="M_core",
            start_line=1,
            end_line=5,
            visibility="public",
            doc="",
        )
        self.symbol_helper = Symbol(
            id="S_utils.helper",
            name="helper",
            qualified_name="helper",
            type="function",
            signature="helper()",
            file_id="F_helpers",
            module_id="M_utils",
            start_line=1,
            end_line=5,
            visibility="public",
            doc="",
        )

    def test_calculate_all_metrics(self) -> None:
        initial_result = RetrievalResult(
            anchor=self.anchor,
            current_object=self.symbol_main,
            related_objects=[self.file_main, self.module_core, self.symbol_helper],
            relations=[
                Relation(
                    id="R_1",
                    relation_type="calls",
                    source_id="S_core.main",
                    target_id="S_utils.helper",
                    source_type="symbol",
                    target_type="symbol",
                    source_module_id="M_core",
                    target_module_id="M_utils",
                )
            ],
            object_scores={
                "S_core.main": 1.0,
                "F_main": 0.8,
                "M_core": 0.7,
                "S_utils.helper": 0.2,
            },
        )
        final_result = RetrievalResult(
            anchor=self.anchor,
            current_object=self.symbol_main,
            related_objects=[self.file_main, self.module_core, self.file_helpers, self.symbol_helper],
            object_scores={
                "S_core.main": 1.0,
                "F_main": 0.8,
                "M_core": 0.7,
                "F_helpers": 0.85,
                "S_utils.helper": 0.2,
            },
        )

        metrics = self.calculator.calculate(
            anchor=self.anchor,
            initial_result=initial_result,
            final_result=final_result,
            expanded_object_ids=["F_helpers", "S_utils.helper"],
        )

        self.assertEqual(metrics.A, 0.75)
        self.assertEqual(metrics.C, 0.75)
        self.assertEqual(metrics.E, 1.0)
        self.assertEqual(metrics.G, 0.5)
        self.assertGreaterEqual(metrics.R, 0.0)
        self.assertLess(metrics.R, 1.0)


if __name__ == "__main__":
    unittest.main()
