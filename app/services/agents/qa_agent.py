"""Basic code QA agent."""

from __future__ import annotations

from typing import Protocol

from app.core.config import settings
from app.models.anchor import Anchor
from app.models.qa_models import CodeSelection, QAResponse
from app.services.context.context_builder import ContextBuilder
from app.services.memory.memory_manager import MemoryManager
from app.services.retrieval.anchor_resolver import AnchorResolver
from app.services.retrieval.retriever import Retriever
from app.storage.repositories import GraphRepository

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
        self.retriever = retriever or Retriever(repository)
        self.context_builder = context_builder or ContextBuilder()
        self.llm_client = llm_client or OpenAICompatibleClient()

    def answer(
        self,
        repo_id: str,
        question: str,
        selection: CodeSelection | None,
        session_id: str,
    ) -> QAResponse:
        _ = repo_id
        memory = self.memory_manager.get_anchor_memory(session_id)
        anchor = self.anchor_resolver.resolve_anchor(question=question, selection=selection, memory=memory)
        retrieval_result = self.retriever.retrieve(anchor=anchor, question=question)
        context = self.context_builder.build_context(
            question=question,
            selection=selection,
            anchor=anchor,
            retrieval_result=retrieval_result,
        )

        if anchor.level == "none":
            answer_text = "无法从当前问题或选择中定位代码锚点，请提供文件或代码片段。"
            need_more_context = True
        else:
            answer_text = self.llm_client.generate(context)
            need_more_context = False
            self.memory_manager.update_anchor_memory(session_id, anchor)

        used_objects = []
        if retrieval_result.current_object is not None:
            used_objects.append(retrieval_result.current_object.id)
        used_objects.extend(object_.id for object_ in retrieval_result.related_objects)

        return QAResponse(
            answer=answer_text,
            anchor=anchor,
            confidence=anchor.confidence,
            used_objects=list(dict.fromkeys(used_objects)),
            need_more_context=need_more_context,
        )
