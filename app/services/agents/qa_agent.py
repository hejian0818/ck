"""Basic code QA agent."""

from __future__ import annotations

import time
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import metrics
from app.models.anchor import Anchor
from app.models.qa_models import CodeSelection, QAResponse, RetrievalResult
from app.services.agents.metrics import Metrics, MetricsCalculator
from app.services.agents.strategy import Strategy, StrategyExecutionContext, StrategyRouter
from app.services.context.context_builder import ContextBuilder
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.memory.memory_manager import MemoryManager
from app.services.retrieval.anchor_resolver import AnchorResolver
from app.services.retrieval.retriever import Retriever
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


class LLMClient(Protocol):
    """Protocol for pluggable LLM clients."""

    def generate(self, prompt: str) -> str:
        """Generate a response from the prompt."""


class OpenAICompatibleClient:
    """OpenAI-compatible chat completion wrapper."""

    def __init__(self) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package is required for LLM calls")
        self.client = OpenAI(base_url=settings.LLM_API_BASE, api_key=settings.LLM_API_KEY)

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


class QAAgent:
    """Coordinate anchor resolution, retrieval, context building, and generation."""

    logger = get_logger(__name__)

    def __init__(
        self,
        repository: GraphRepository,
        memory_manager: MemoryManager | None = None,
        anchor_resolver: AnchorResolver | None = None,
        retriever: Retriever | None = None,
        context_builder: ContextBuilder | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.memory_manager = memory_manager or MemoryManager()
        self.anchor_resolver = anchor_resolver or AnchorResolver(repository)
        self.retriever = retriever or Retriever(
            repository,
            embedding_builder=EmbeddingBuilder(),
            vector_store=VectorStore(settings.DATABASE_URL),
        )
        self.context_builder = context_builder or ContextBuilder()
        self.llm_client = llm_client or OpenAICompatibleClient()
        self.metrics_calculator = MetricsCalculator()
        self.strategy_router = StrategyRouter()

    def answer(
        self,
        repo_id: str,
        question: str,
        selection: CodeSelection | None,
        session_id: str,
    ) -> QAResponse:
        _ = repo_id
        started_at = time.perf_counter()
        memory = self.memory_manager.get_anchor_memory(session_id)
        anchor = self.anchor_resolver.resolve_anchor(question=question, selection=selection, memory=memory)
        initial_result = self.retriever.retrieve(
            anchor=anchor,
            question=question,
            repo_id=repo_id,
            memory=memory,
        )

        initial_metrics = self.metrics_calculator.calculate(
            anchor=anchor,
            initial_result=initial_result,
            final_result=initial_result,
        )
        strategy = self.strategy_router.determine_strategy(initial_metrics)
        execution = self.strategy_router.execute_strategy(
            strategy=strategy,
            context=StrategyExecutionContext(
                question=question,
                anchor=anchor,
                initial_result=initial_result,
                retriever=self.retriever,
                memory=memory,
            ),
        )

        final_metrics = self.metrics_calculator.calculate(
            anchor=anchor,
            initial_result=initial_result,
            final_result=execution.retrieval_result,
            expanded_object_ids=execution.expanded_object_ids,
        )
        degraded = execution.strategy == Strategy.S4 or self.strategy_router.should_degrade(final_metrics)
        strategy_used = Strategy.S4 if degraded else execution.strategy
        suggestions = list(execution.suggestions)

        if degraded:
            answer_text, suggestions = self._build_degraded_answer(
                anchor=anchor,
                retrieval_result=execution.retrieval_result,
                metrics=final_metrics,
                suggestions=suggestions,
            )
            need_more_context = True
        elif anchor.level == "none":
            answer_text = "无法从当前问题或选择中定位代码锚点，请提供文件或代码片段。"
            suggestions = [
                "请提供文件路径或函数名。",
                "请附上相关代码片段，便于定位锚点。",
            ]
            need_more_context = True
            degraded = True
            strategy_used = Strategy.S4
        else:
            context = self.context_builder.build_context(
                question=question,
                selection=selection,
                anchor=anchor,
                retrieval_result=execution.retrieval_result,
            )
            answer_text = self.llm_client.generate(context)
            need_more_context = False

        used_objects = self._collect_used_objects(execution.retrieval_result)
        recent_subgraph_summary = self._summarize_subgraph(execution.retrieval_result)
        recent_evidence_summary = self._summarize_evidence(execution.retrieval_result)

        if anchor.level != "none":
            self.memory_manager.update_anchor_memory(session_id, anchor)
        self.memory_manager.update_retrieval_memory(
            session_id=session_id,
            anchor=anchor,
            retrieval_result=execution.retrieval_result,
            recent_subgraph_summary=recent_subgraph_summary,
            recent_evidence_summary=recent_evidence_summary,
        )
        self.memory_manager.update_focus_memory(session_id, question)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        metrics.increment("qa.requests")
        metrics.observe("qa.latency_ms", elapsed_ms)
        metrics.increment(f"qa.strategy.{strategy_used.value}")
        if degraded:
            metrics.increment("qa.degraded")
        self.logger.info(
            "qa_answer",
            extra={
                "context": {
                    "session_id": session_id,
                    "anchor": {
                        "level": anchor.level,
                        "confidence": anchor.confidence,
                    },
                    "metrics": final_metrics.model_dump(),
                    "strategy": strategy_used.value,
                    "degraded": degraded,
                    "used_objects": used_objects,
                    "elapsed_ms": elapsed_ms,
                }
            },
        )

        return QAResponse(
            answer=answer_text,
            anchor=anchor,
            confidence=anchor.confidence,
            used_objects=used_objects,
            need_more_context=need_more_context,
            strategy_used=strategy_used.value,
            metrics=final_metrics,
            degraded=degraded,
            suggestions=suggestions,
        )

    @staticmethod
    def _collect_used_objects(retrieval_result: RetrievalResult) -> list[str]:
        used_objects: list[str] = []
        if retrieval_result.current_object is not None:
            used_objects.append(retrieval_result.current_object.id)
        used_objects.extend(object_.id for object_ in retrieval_result.related_objects)
        return list(dict.fromkeys(used_objects))

    @staticmethod
    def _summarize_subgraph(retrieval_result: RetrievalResult) -> str:
        current_id = retrieval_result.current_object.id if retrieval_result.current_object is not None else "none"
        related_ids = [object_.id for object_ in retrieval_result.related_objects[:5]]
        return f"current={current_id}; related={','.join(related_ids) if related_ids else 'none'}"

    @staticmethod
    def _summarize_evidence(retrieval_result: RetrievalResult) -> str:
        ranked_scores = sorted(
            retrieval_result.object_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        if not ranked_scores:
            return "no_evidence"
        return ", ".join(f"{object_id}:{score:.2f}" for object_id, score in ranked_scores)

    def _build_degraded_answer(
        self,
        anchor: Anchor,
        retrieval_result: RetrievalResult,
        metrics: Metrics,
        suggestions: list[str],
    ) -> tuple[str, list[str]]:
        used_objects = self._collect_used_objects(retrieval_result)
        scores = retrieval_result.object_scores

        # --- Partial answer mode ---
        high_score_threshold = 0.6
        high_score_objects = [oid for oid in used_objects if scores.get(oid, 0.0) >= high_score_threshold]
        low_score_objects = [oid for oid in used_objects if scores.get(oid, 0.0) < high_score_threshold]

        if high_score_objects and low_score_objects:
            confident_part = "、".join(high_score_objects[:5])
            uncertain_part = "、".join(low_score_objects[:5])
            answer = (
                f"部分确认: {confident_part}。"
                f" 以下部分证据不足 [不确定]: {uncertain_part}。"
            )
            suggestions = suggestions or [
                "请补充不确定部分的更多上下文。",
                "可以针对确认部分继续追问细节。",
            ]
            return answer, suggestions

        # --- Multi-candidate mode ---
        if metrics.C < 0.5 and len(used_objects) >= 2:
            candidates = used_objects[:3]
            candidate_lines = [f"  {i + 1}. {oid}" for i, oid in enumerate(candidates)]
            answer = "当前检索结果分散，可能的解释方向:\n" + "\n".join(candidate_lines)
            suggestions = suggestions or [
                "请指出更具体的文件、类或函数。",
                "可以限定你关心的是实现、调用关系还是模块职责。",
            ]
            return answer, suggestions

        # --- Guided follow-up ---
        if anchor.level == "module":
            answer = "目前定位在模块级别，信息较为宏观。"
            if used_objects:
                answer += " 已定位到: " + "、".join(used_objects[:3]) + "。"
            suggestions = suggestions or [
                "请指定模块内的具体文件以获取更详细的信息。",
                "可以询问模块内特定类或函数的实现细节。",
                "尝试提供文件路径来缩小范围。",
            ]
            return answer, suggestions

        if anchor.level == "file":
            answer = "目前定位在文件级别，可进一步深入到具体符号。"
            if used_objects:
                answer += " 已定位到: " + "、".join(used_objects[:3]) + "。"
            suggestions = suggestions or [
                "请指定文件内的具体函数或类。",
                "可以询问文件中特定方法的调用关系。",
                "尝试提供行号范围来精确定位。",
            ]
            return answer, suggestions

        if anchor.level == "symbol" and used_objects:
            answer = "目前定位在符号级别，已定位到: " + "、".join(used_objects[:3]) + "。其余部分证据不足。"
            suggestions = suggestions or [
                "请补充相关调用链或相邻代码片段。",
                "如果需要更完整答案，请缩小到一个函数或文件范围。",
            ]
            return answer, suggestions

        answer = "当前上下文不足，无法可靠回答该问题。"
        suggestions = suggestions or [
            "请提供具体代码片段。",
            "请说明目标文件、模块或函数名。",
        ]
        return answer, suggestions
