"""Strategy router tests."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol
from app.models.qa_models import RetrievalResult
from app.services.agents.metrics import Metrics
from app.services.agents.strategy import Strategy, StrategyExecutionContext, StrategyRouter


class _RetrieverStub:
    def __init__(self) -> None:
        self.retrieved_anchors: list[Anchor] = []

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
        self.retrieved_anchors.append(anchor)
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

    def test_execute_strategy_infers_file_anchor_from_concentrated_results(self) -> None:
        anchor = Anchor(level="none", source="none", confidence=0.0)
        file_obj = File(
            id="F_demo",
            name="demo.py",
            path="demo.py",
            module_id="M_demo",
            language="python",
            start_line=1,
            end_line=20,
        )
        symbols = [
            Symbol(
                id=f"S_demo.item_{index}",
                name=f"item_{index}",
                qualified_name=f"item_{index}",
                type="function",
                signature=f"item_{index}()",
                file_id="F_demo",
                module_id="M_demo",
                start_line=index,
                end_line=index,
                visibility="public",
                doc="",
            )
            for index in range(3)
        ]
        initial_result = RetrievalResult(anchor=anchor, related_objects=[file_obj, *symbols])
        retriever = _RetrieverStub()

        execution = self.router.execute_strategy(
            strategy=Strategy.S3,
            context=StrategyExecutionContext(
                question="这里的逻辑是什么？",
                anchor=anchor,
                initial_result=initial_result,
                retriever=retriever,
            ),
        )

        self.assertEqual(execution.strategy, Strategy.S3)
        self.assertEqual(retriever.retrieved_anchors[-1].level, "file")
        self.assertEqual(retriever.retrieved_anchors[-1].file_id, "F_demo")
        self.assertEqual(retriever.retrieved_anchors[-1].source, "retrieval_infer")
        self.assertEqual(retriever.retrieved_anchors[-1].confidence, 0.60)

    def test_execute_strategy_infers_module_anchor_when_file_concentration_is_low(self) -> None:
        anchor = Anchor(level="none", source="none", confidence=0.0)
        files = [
            File(
                id=f"F_demo_{index}",
                name=f"demo_{index}.py",
                path=f"demo_{index}.py",
                module_id="M_demo",
                language="python",
                start_line=1,
                end_line=20,
            )
            for index in range(3)
        ]
        module = Module(id="M_demo", name="demo", path="demo", metadata={})
        initial_result = RetrievalResult(anchor=anchor, related_objects=[module, *files])
        retriever = _RetrieverStub()

        execution = self.router.execute_strategy(
            strategy=Strategy.S3,
            context=StrategyExecutionContext(
                question="这个模块负责什么？",
                anchor=anchor,
                initial_result=initial_result,
                retriever=retriever,
            ),
        )

        self.assertEqual(execution.strategy, Strategy.S3)
        self.assertEqual(retriever.retrieved_anchors[-1].level, "module")
        self.assertEqual(retriever.retrieved_anchors[-1].module_id, "M_demo")
        self.assertEqual(retriever.retrieved_anchors[-1].source, "retrieval_infer")
        self.assertEqual(retriever.retrieved_anchors[-1].confidence, 0.55)

    def test_execute_strategy_falls_back_to_s4_when_concentration_is_low(self) -> None:
        anchor = Anchor(level="none", source="none", confidence=0.0)
        files = [
            File(
                id=f"F_demo_{index}",
                name=f"demo_{index}.py",
                path=f"demo_{index}.py",
                module_id=f"M_demo_{index}",
                language="python",
                start_line=1,
                end_line=20,
            )
            for index in range(3)
        ]
        initial_result = RetrievalResult(anchor=anchor, related_objects=files)
        retriever = _RetrieverStub()

        execution = self.router.execute_strategy(
            strategy=Strategy.S3,
            context=StrategyExecutionContext(
                question="这里是什么？",
                anchor=anchor,
                initial_result=initial_result,
                retriever=retriever,
            ),
        )

        self.assertEqual(execution.strategy, Strategy.S4)
        self.assertEqual(retriever.retrieved_anchors, [])
        self.assertEqual(execution.retrieval_result, initial_result)


if __name__ == "__main__":
    unittest.main()
