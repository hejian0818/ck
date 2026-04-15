"""Vector store tests."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.models.vector_models import Embedding
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore


class _ConnectionContext:
    def __init__(self, connection) -> None:  # noqa: ANN001
        self.connection = connection

    def __enter__(self):  # noqa: ANN204
        return self.connection

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, ANN204
        return False


class _Row:
    def __init__(self, **values: object) -> None:
        self._mapping = values
        self._values = list(values.values())

    def __getitem__(self, index: int) -> object:
        return self._values[index]


class VectorStoreTests(unittest.TestCase):
    def test_save_embeddings_uses_bulk_upsert(self) -> None:
        connection = Mock()
        engine = Mock()
        engine.begin.return_value = _ConnectionContext(connection)
        store = VectorStore(database_url="postgresql://localhost/test", engine=engine)

        store.save_embeddings(
            [
                Embedding(
                    repo_id="repo_test",
                    object_id="S_1",
                    object_type="symbol",
                    embedding=[0.1, 0.2],
                )
            ]
        )

        statement, params = connection.execute.call_args[0]
        self.assertIn("ON CONFLICT (repo_id, object_id)", statement.text)
        self.assertEqual(
            params,
            [
                {
                    "repo_id": "repo_test",
                    "object_id": "S_1",
                    "object_type": "symbol",
                    "embedding": "[0.1, 0.2]",
                }
            ],
        )

    def test_get_embedding_parses_pgvector_text(self) -> None:
        connection = Mock()
        connection.execute.return_value.fetchone.return_value = _Row(embedding="[0.1,0.2,0.3]")
        engine = Mock()
        engine.connect.return_value = _ConnectionContext(connection)
        store = VectorStore(database_url="postgresql://localhost/test", engine=engine)

        embedding = store.get_embedding(repo_id="repo_test", object_id="S_1")

        self.assertEqual(embedding, [0.1, 0.2, 0.3])

    def test_search_similar_filters_by_type_and_metric(self) -> None:
        connection = Mock()
        connection.execute.return_value.fetchall.return_value = [
            _Row(object_id="S_1", object_type="symbol", similarity=0.91),
        ]
        engine = Mock()
        engine.connect.return_value = _ConnectionContext(connection)
        store = VectorStore(database_url="postgresql://localhost/test", engine=engine)

        results = store.search_similar(
            repo_id="repo_test",
            query_vector=[0.2, 0.8],
            object_type="symbol",
            top_k=5,
            min_similarity=0.4,
            metric="inner_product",
        )

        statement, params = connection.execute.call_args[0]
        self.assertIn("embedding <#> CAST(:query_vector AS vector)", statement.text)
        self.assertIn("object_type = :object_type", statement.text)
        self.assertEqual(params["object_type"], "symbol")
        self.assertEqual(results[0].object_id, "S_1")
        self.assertEqual(results[0].similarity, 0.91)

    def test_search_symbols_uses_default_bucket_size(self) -> None:
        store = VectorStore(database_url="postgresql://localhost/test", engine=Mock())

        with patch.object(store, "search_similar", return_value=[]) as search_similar:
            store.search_symbols(repo_id="repo_test", query_vector=[0.1, 0.2])

        search_similar.assert_called_once_with(
            repo_id="repo_test",
            query_vector=[0.1, 0.2],
            object_type="symbol",
            top_k=20,
            min_similarity=0.5,
            metric="cosine",
        )

    def test_search_similar_rejects_unknown_metric(self) -> None:
        store = VectorStore(database_url="postgresql://localhost/test", engine=Mock())

        with self.assertRaises(ValueError):
            store.search_similar(repo_id="repo_test", query_vector=[1.0], metric="dot")

    def test_sqlite_vector_store_saves_and_searches_in_python(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        repository = GraphRepository(database_url="sqlite://", engine=engine)
        repository.init_vector_tables()
        store = VectorStore(database_url="sqlite://", engine=engine)

        store.save_embeddings(
            [
                Embedding(repo_id="repo_test", object_id="S_close", object_type="symbol", embedding=[1.0, 0.0]),
                Embedding(repo_id="repo_test", object_id="S_far", object_type="symbol", embedding=[0.0, 1.0]),
            ]
        )

        results = store.search_symbols(repo_id="repo_test", query_vector=[1.0, 0.0], top_k=1, min_similarity=0.0)

        self.assertEqual([result.object_id for result in results], ["S_close"])
        self.assertEqual(store.get_embedding("repo_test", "S_close"), [1.0, 0.0])


if __name__ == "__main__":
    unittest.main()
