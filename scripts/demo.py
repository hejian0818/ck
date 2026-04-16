"""End-to-end demo: scan repo → build graph → QA → document generation.

Usage: python3 scripts/demo.py
Uses a local sqlite repository plus deterministic stubs for embeddings and LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.qa_models import CodeSelection
from app.services.agents.doc_agent import DeterministicDocLLMClient, DocAgent, SkeletonPlanner
from app.services.agents.qa_agent import QAAgent
from app.services.cleanarch.graph_builder import GraphBuilder
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.memory.memory_manager import MemoryManager
from app.services.retrieval.doc_retriever import DocRetriever
from app.services.retrieval.retriever import Retriever
from app.services.review.doc_reviewer import DocumentReviewer
from app.storage.repositories import GraphRepository


class _DemoEmbeddingBuilder(EmbeddingBuilder):
    """Deterministic embedding builder for offline demo runs."""

    def __init__(self) -> None:
        super().__init__(provider="sentence-transformer", dimension=8, batch_size=8)

    def encode_summaries(self, summaries: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for summary in summaries:
            base = sum(ord(char) for char in summary) or 1
            vector = [float(((base + index * 17) % 97) + 1) for index in range(self.dimension)]
            vectors.append(self._normalize_vector(vector))
        return vectors


class _DemoVectorStore:
    """In-memory vector search store for the demo."""

    def __init__(self) -> None:
        self._items: list[tuple[str, str, str, list[float]]] = []

    def save_embeddings(self, embeddings) -> None:
        self._items = [
            (embedding.repo_id, embedding.object_id, embedding.object_type, embedding.embedding)
            for embedding in embeddings
        ]

    def _search(self, repo_id: str, query_vector: list[float], object_type: str | None, top_k: int) -> list[SimpleNamespace]:
        scored: list[SimpleNamespace] = []
        for item_repo_id, object_id, item_type, vector in self._items:
            if item_repo_id != repo_id:
                continue
            if object_type is not None and item_type != object_type:
                continue
            similarity = sum(left * right for left, right in zip(query_vector, vector, strict=True))
            scored.append(SimpleNamespace(object_id=object_id, object_type=item_type, similarity=similarity))
        scored.sort(key=lambda item: item.similarity, reverse=True)
        return scored[:top_k]

    def search_symbols(self, repo_id: str, query_vector: list[float], top_k: int = 10, **_kwargs):
        return self._search(repo_id, query_vector, "symbol", top_k)

    def search_files(self, repo_id: str, query_vector: list[float], top_k: int = 10, **_kwargs):
        return self._search(repo_id, query_vector, "file", top_k)

    def search_modules(self, repo_id: str, query_vector: list[float], top_k: int = 10, **_kwargs):
        return self._search(repo_id, query_vector, "module", top_k)

    def search_relations(self, repo_id: str, query_vector: list[float], top_k: int = 10, **_kwargs):
        return self._search(repo_id, query_vector, "relation", top_k)


class _DemoLLMClient:
    """Deterministic QA LLM stub for demo output."""

    def generate(self, prompt: str) -> str:
        lines = [line for line in prompt.splitlines() if line.strip()]
        question = next((line.replace("当前问题: ", "") for line in lines if line.startswith("当前问题: ")), "<unknown>")
        anchor = next((line.replace("- 对象: ", "") for line in lines if line.startswith("- 对象: ")), "<unknown>")
        return f"Demo answer: 问题“{question}”当前主要定位到 {anchor}，可结合上下文继续深入。"


def _build_repository() -> GraphRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    repository = GraphRepository(database_url="sqlite://", engine=engine)
    repository.initialize_schema()
    return repository


def main() -> None:
    repo_path = PROJECT_ROOT / "data" / "test_repo"
    output_dir = PROJECT_ROOT / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    repository = _build_repository()
    embedding_builder = _DemoEmbeddingBuilder()
    vector_store = _DemoVectorStore()
    memory_manager = MemoryManager()

    print("=" * 60)
    print("CK Demo - End-to-End Repository Analysis")
    print("=" * 60)

    print("\n[1/5] Scanning repository and building graph ...")
    graph_builder = GraphBuilder(
        embedding_builder=embedding_builder,
        vector_store=vector_store,
    )
    graph = graph_builder.build_graph(repo_path=str(repo_path), branch="main")
    repository.save_graphcode(graph)
    print(
        f"  repo_id={graph.repo_meta.repo_id} modules={len(graph.modules)} files={len(graph.files)} "
        f"symbols={len(graph.symbols)} relations={len(graph.relations)}"
    )

    print("\n[2/5] Verifying embedding generation ...")
    embedding_count = len(vector_store._items)
    print(f"  Stored {embedding_count} embeddings in demo vector store")

    print("\n[3/5] Running QA example ...")
    qa_agent = QAAgent(
        repository=repository,
        memory_manager=memory_manager,
        retriever=Retriever(repository),
        llm_client=_DemoLLMClient(),
    )
    qa_response = qa_agent.answer(
        repo_id=graph.repo_meta.repo_id,
        question="GreetingService.greet 做什么？",
        selection=CodeSelection(
            file_path="app_core/services.py",
            line_start=9,
            line_end=10,
        ),
        session_id="demo-session",
    )
    print(f"  Answer: {qa_response.answer}")
    print(f"  Strategy: {qa_response.strategy_used}, degraded={qa_response.degraded}")

    print("\n[4/5] Generating design document ...")
    planner = SkeletonPlanner(repository)
    doc_agent = DocAgent(
        repository=repository,
        planner=planner,
        retriever=DocRetriever(repository, embedding_builder=embedding_builder, vector_store=vector_store),
        llm_client=DeterministicDocLLMClient(),
        memory_manager=memory_manager,
        reviewer=DocumentReviewer(repository),
    )
    skeleton = doc_agent.plan(graph.repo_meta.repo_id)
    document = doc_agent.generate(graph.repo_meta.repo_id, skeleton)
    print(f"  Planned {len(skeleton.sections)} sections")
    print(f"  Generated {len(document.sections)} sections")

    print("\n[5/5] Writing outputs ...")
    document_path = output_dir / "demo_document.md"
    qa_path = output_dir / "demo_qa.txt"

    lines = [f"# {document.title}", ""]
    for section in document.sections:
        lines.append(section.content)
        for diagram in section.diagrams:
            lines.extend(["", "```plantuml", diagram, "```"])
        lines.append("")
    document_path.write_text("\n".join(lines), encoding="utf-8")

    qa_lines = [
        "Question: GreetingService.greet 做什么？",
        f"Answer: {qa_response.answer}",
        f"Anchor: {qa_response.anchor.model_dump()}",
        f"Used objects: {', '.join(qa_response.used_objects)}",
        f"Strategy: {qa_response.strategy_used}",
    ]
    qa_path.write_text("\n".join(qa_lines), encoding="utf-8")
    print(f"  Document written to: {document_path}")
    print(f"  QA output written to: {qa_path}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print(f"  Repo path: {repo_path}")
    print(f"  Repo ID: {graph.repo_meta.repo_id}")
    print(f"  Embeddings: {embedding_count}")
    print(f"  QA answer degraded: {qa_response.degraded}")
    print(f"  Output dir: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
