"""Embedding builder tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.graph_objects import File, GraphCode, Module, Relation, RepoMeta, Span, Symbol
from app.services.indexing.embedding_builder import EmbeddingBuilder


class _SentenceTransformerStub:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, summaries, **kwargs):  # noqa: ANN001
        self.calls.append(list(summaries))
        return [[3.0, 4.0] for _ in summaries]


class _OpenAIEmbeddingsStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, *, model: str, input):  # noqa: A002, ANN001
        self.calls.append({"model": model, "input": list(input)})
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.0, 2.0]) for _ in input],
        )


class _OpenAIClientStub:
    def __init__(self) -> None:
        self.embeddings = _OpenAIEmbeddingsStub()


class _FallbackBuilder(EmbeddingBuilder):
    def encode_summaries(self, summaries: list[str]) -> list[list[float]]:
        if len(summaries) > 1:
            raise RuntimeError("batch failed")
        return [self.encode_summary(summaries[0])]

    def encode_summary(self, summary: str) -> list[float]:
        if summary == "skip me":
            raise RuntimeError("single failed")
        return [1.0, 0.0]


class EmbeddingBuilderTests(unittest.TestCase):
    def test_sentence_transformer_builder_batches_and_normalizes(self) -> None:
        model = _SentenceTransformerStub()
        builder = EmbeddingBuilder(
            provider="sentence-transformer",
            batch_size=2,
            dimension=2,
            sentence_transformer_model=model,
        )

        embeddings = builder.build_embeddings(self._build_graph())

        self.assertEqual(len(embeddings), 4)
        self.assertEqual(model.calls, [["module summary", "file summary"], ["symbol summary", "relation summary"]])
        self.assertEqual(embeddings[0].object_type, "module")
        self.assertEqual(embeddings[0].embedding, [0.6, 0.8])

    def test_openai_builder_encodes_single_summary(self) -> None:
        client = _OpenAIClientStub()
        builder = EmbeddingBuilder(
            provider="openai",
            model_name="text-embedding-test",
            dimension=2,
            openai_client=client,
        )

        vector = builder.encode_summary("hello")

        self.assertEqual(vector, [0.0, 1.0])
        self.assertEqual(client.embeddings.calls, [{"model": "text-embedding-test", "input": ["hello"]}])

    def test_build_embeddings_retries_failed_batch_and_skips_failed_objects(self) -> None:
        builder = _FallbackBuilder(provider="sentence-transformer", batch_size=2, dimension=2)
        graph = self._build_graph()
        graph = graph.model_copy(
            update={
                "relations": [
                    graph.relations[0].model_copy(update={"summary": "skip me"}),
                ]
            }
        )

        embeddings = builder.build_embeddings(graph)

        self.assertEqual([embedding.object_id for embedding in embeddings], ["M_app", "F_app", "S_app.func"])

    @staticmethod
    def _build_graph() -> GraphCode:
        repo_meta = RepoMeta(
            repo_id="repo_test",
            repo_path="/tmp/repo",
            branch="main",
            commit_hash="abc123",
            scan_time=datetime.now(timezone.utc),
        )
        module = Module(id="M_app", name="app", path="app", summary="module summary", metadata={})
        file_obj = File(
            id="F_app",
            name="app.py",
            path="app.py",
            module_id="M_app",
            summary="file summary",
            language="python",
            start_line=1,
            end_line=10,
        )
        symbol = Symbol(
            id="S_app.func",
            name="func",
            qualified_name="app.func",
            type="function",
            signature="func()",
            file_id="F_app",
            module_id="M_app",
            summary="symbol summary",
            start_line=1,
            end_line=2,
            visibility="public",
            doc="",
        )
        relation = Relation(
            id="R_1",
            relation_type="calls",
            source_id="S_app.func",
            target_id="S_app.other",
            source_type="symbol",
            target_type="symbol",
            source_module_id="M_app",
            target_module_id="M_app",
            summary="relation summary",
        )
        return GraphCode(
            repo_meta=repo_meta,
            modules=[module],
            files=[file_obj],
            symbols=[symbol],
            relations=[relation],
            spans=[
                Span(
                    file_path="app.py",
                    line_start=1,
                    line_end=10,
                    module_id="M_app",
                    file_id="F_app",
                    node_type="file",
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
