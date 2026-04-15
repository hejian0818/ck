"""PostgreSQL + pgvector integration smoke tests."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.models.graph_objects import File, GraphCode, Module, Relation, RepoMeta, Span, Symbol
from app.models.vector_models import Embedding
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore


class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database_url = os.getenv("PGVECTOR_TEST_URL")
        if not database_url:
            raise unittest.SkipTest("PGVECTOR_TEST_URL is not set")

        cls.engine = create_engine(database_url)
        with cls.engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        cls.repository = GraphRepository(database_url=database_url, engine=cls.engine)
        cls.repository.initialize_schema()
        cls.repository.init_vector_tables()
        cls.vector_store = VectorStore(database_url=database_url, engine=cls.engine)

    def test_repository_and_vector_store_round_trip(self) -> None:
        repo_suffix = uuid4().hex[:8]
        repo_id = f"repo_pg_{repo_suffix}"
        module = Module(id=f"M_{repo_suffix}", name="core", path="core", metadata={})
        file_obj = File(
            id=f"F_{repo_suffix}",
            name="main.py",
            path="core/main.py",
            module_id=module.id,
            content_hash="hash-main",
            language="python",
            start_line=1,
            end_line=10,
        )
        symbol = Symbol(
            id=f"S_{repo_suffix}",
            name="run",
            qualified_name="core.run",
            type="function",
            signature="run()",
            file_id=file_obj.id,
            module_id=module.id,
            start_line=1,
            end_line=3,
            visibility="public",
            doc="",
        )
        relation = Relation(
            id=f"R_{repo_suffix}",
            relation_type="exports",
            source_id=symbol.id,
            target_id="export:run",
            source_type="symbol",
            target_type="external",
            source_module_id=module.id,
            target_module_id=module.id,
        )
        graph = GraphCode(
            repo_meta=RepoMeta(
                repo_id=repo_id,
                repo_path=f"/tmp/{repo_id}",
                branch="main",
                commit_hash="abc123",
                scan_time=datetime.now(timezone.utc),
            ),
            modules=[module],
            files=[file_obj],
            symbols=[symbol],
            relations=[relation],
            spans=[
                Span(
                    file_path=file_obj.path,
                    line_start=1,
                    line_end=10,
                    module_id=module.id,
                    file_id=file_obj.id,
                    symbol_id=None,
                    node_type="file",
                )
            ],
        )

        self.repository.save_graphcode(graph)
        loaded_graph = self.repository.load_graphcode(repo_id)
        self.assertIsNotNone(loaded_graph)
        assert loaded_graph is not None
        self.assertEqual(len(loaded_graph.files), 1)
        self.assertEqual(loaded_graph.files[0].content_hash, "hash-main")

        self.vector_store.save_embeddings(
            [
                Embedding(repo_id=repo_id, object_id=symbol.id, object_type="symbol", embedding=[1.0, 0.0]),
                Embedding(repo_id=repo_id, object_id=file_obj.id, object_type="file", embedding=[0.0, 1.0]),
            ]
        )
        results = self.vector_store.search_symbols(
            repo_id=repo_id,
            query_vector=[1.0, 0.0],
            top_k=1,
            min_similarity=0.0,
        )
        self.assertEqual([result.object_id for result in results], [symbol.id])


if __name__ == "__main__":
    unittest.main()
