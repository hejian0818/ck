"""Strategy router tests."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol
from app.models.qa_models import RetrievalResult
from app.services.agents.metrics import Metrics
from app.services.agents.strategy import Strategy, StrategyExecutionContext, StrategyRouter


class _RetrieverStub:
    def expand_retrieval(self, retrieval_result: RetrievalResult, max_depth: int = 2) -> RetrievalResult:
        _ = max_depth
        helper = Symbol(
            id="S_demo.helper",
            name="helper",
            qualified_name="helper",
            type="function",
            signature="helper()",
            file_id="F_demo",
            module_id="M_demo",
            start_line=10,
            end_line=12,
            visibility="public",
            doc="",
        )
        return retrieval_result.model_copy(
            update={
                "related_objects": retrieval_result.related_objects + [helper],
                "object_scores": {**retrieval_result.object_scores, helper.id: 0.85},
            }
        )

    def retrieve(self, anchor: Anchor, question: str) -> RetrievalResult:
        _ = question
        symbol = Symbol(
            id=anchor.symbol_id or "S_demo.entry",
            name="entry",
            qualified_name="entry",
            type="function",
            signature="entry()",
            file_id="F_demo",
            module_id="M_demo",
            start_line=1,
            end_line=3,
            visibility="public",
            doc="",
        )
        file_obj = File(
            id="F_demo",
            name="demo.py",
            path="demo.py",
            module_id="M_demo",
            language="python",
            start_line=1,
            end_line=20,
        )
        module = Module(id="M_demo", name="demo", path="demo", metadata={})
        return RetrievalResult(
            anchor=anchor,
            current_object=symbol,
            related_objects=[file_obj, module],
            object_scores={symbol.id: 1.0, file_obj.id: 0.8, module.id: 0.7},
        )


class StrategyRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = StrategyRouter()

    def test_determine_strategy_routes_all_states(self) -> None:
        self.assertEqual(
            self.router.determine_strategy(Metrics(A=0.85, C=0.8, E=0.7, G=0.5, R=0.8)),
            Strategy.S1,
        )
        self.assertEqual(
            self.router.determine_strategy(Metrics(A=0.65, C=0.5, E=0.5, G=0.5, R=0.8)),
            Strategy.S2,
        )
        self.assertEqual(
            self.router.determine_strategy(Metrics(A=0.5, C=0.6, E=0.7, G=0.5, R=0.8)),
            Strategy.S3,
        )
        self.assertEqual(
            self.router.determine_strategy(Metrics(A=0.35, C=0.7, E=0.7, G=0.5, R=0.8)),
            Strategy.S4,
        )

    def test_execute_strategy_expands_results_for_s2(self) -> None:
        anchor = Anchor(level="symbol", source="explicit_span", confidence=0.7, symbol_id="S_demo.entry")
        base_result = _RetrieverStub().retrieve(anchor, "这个函数做什么？")
        execution = self.router.execute_strategy(
            strategy=Strategy.S2,
            context=StrategyExecutionContext(
                question="这个函数做什么？",
                anchor=anchor,
                initial_result=base_result,
                retriever=_RetrieverStub(),
            ),
        )
        self.assertEqual(execution.strategy, Strategy.S2)
        self.assertIn("S_demo.helper", [object_.id for object_ in execution.retrieval_result.related_objects])
        self.assertEqual(execution.expanded_object_ids, ["S_demo.helper"])


if __name__ == "__main__":
    unittest.main()
