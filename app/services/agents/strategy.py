"""Strategy routing for QA retrieval flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.core import thresholds
from app.models.anchor import Anchor
from app.models.qa_models import RetrievalResult
from app.services.agents.metrics import Metrics


class Strategy(StrEnum):
    """Supported QA strategies."""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


@dataclass(slots=True)
class StrategyExecutionContext:
    """Execution context for a chosen strategy."""

    question: str
    anchor: Anchor
    initial_result: RetrievalResult
    retriever: Any
    memory: Any = None


@dataclass(slots=True)
class StrategyExecution:
    """Result of a strategy execution."""

    strategy: Strategy
    retrieval_result: RetrievalResult
    expanded_object_ids: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class StrategyRouter:
    """Select and execute QA strategies based on metrics."""

    def determine_strategy(self, metrics: Metrics) -> Strategy:
        """Choose a strategy from the current metrics."""

        if self.should_degrade(metrics):
            return Strategy.S4
        if metrics.A >= thresholds.ANCHOR_CONFIDENCE_STRONG and metrics.E >= thresholds.EVIDENCE_SUFFICIENT:
            return Strategy.S1
        if (
            metrics.A >= thresholds.ANCHOR_CONFIDENCE_WEAK
            and metrics.E < thresholds.EVIDENCE_SUFFICIENT
            and metrics.C >= thresholds.RETRIEVAL_CONCENTRATION_ENHANCED
        ):
            return Strategy.S2
        if metrics.A < thresholds.ANCHOR_CONFIDENCE_WEAK and metrics.C >= thresholds.RETRIEVAL_CONCENTRATION:
            return Strategy.S3
        return Strategy.S4

    def should_degrade(self, metrics: Metrics) -> bool:
        """Return whether the metrics require strategy degradation."""

        return any(
            (
                metrics.A < thresholds.ANCHOR_CONFIDENCE_DEGRADE,
                metrics.C < thresholds.RETRIEVAL_CONCENTRATION_DEGRADE,
                metrics.E < thresholds.EVIDENCE_ENHANCEMENT,
                metrics.R < thresholds.RESULT_CONSISTENCY,
                metrics.G < thresholds.EXPANSION_GAIN,
            )
        )

    def execute_strategy(
        self,
        strategy: Strategy,
        context: StrategyExecutionContext,
    ) -> StrategyExecution:
        """Execute the chosen retrieval strategy."""

        if strategy == Strategy.S1:
            return StrategyExecution(strategy=strategy, retrieval_result=context.initial_result)

        if strategy == Strategy.S2:
            expanded_result = context.retriever.expand_retrieval(context.initial_result, max_depth=2)
            expanded_object_ids = [
                object_.id
                for object_ in expanded_result.related_objects
                if object_.id not in {item.id for item in context.initial_result.related_objects}
            ]
            return StrategyExecution(
                strategy=strategy,
                retrieval_result=expanded_result,
                expanded_object_ids=expanded_object_ids,
            )

        if strategy == Strategy.S3:
            if context.anchor.level != "none":
                inferred_anchor = context.anchor.model_copy(deep=True)
                inferred_anchor.confidence = min(
                    thresholds.ANCHOR_CONFIDENCE_WEAK,
                    max(inferred_anchor.confidence, thresholds.ANCHOR_CONFIDENCE_DEGRADE),
                )
                inferred_anchor.source = "retrieval_infer"
                inferred_result = context.retriever.retrieve(inferred_anchor, context.question)
                return StrategyExecution(strategy=strategy, retrieval_result=inferred_result)

            return StrategyExecution(
                strategy=Strategy.S4,
                retrieval_result=context.initial_result,
                suggestions=[
                    "请提供更具体的文件、函数名或代码片段。",
                    "可以先指出你关心的模块或文件范围。",
                ],
            )

        return StrategyExecution(
            strategy=Strategy.S4,
            retrieval_result=context.initial_result,
            suggestions=[
                "请补充更具体的上下文，例如文件路径、函数名或代码片段。",
                "如果问题范围较大，请拆分为更小的局部问题。",
            ],
        )
