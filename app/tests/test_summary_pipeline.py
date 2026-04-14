"""Summary pipeline and repo API integration tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.graph_objects import GraphCode
from app.models.qa_models import RepoBuildResponse
from app.services.cleanarch.graph_builder import GraphBuilder
from app.storage.repositories import GraphRepository


class SummaryPipelineTests(unittest.TestCase):
    def _build_repository(self) -> GraphRepository:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        repository = GraphRepository(database_url="sqlite://", engine=engine)
        repository.initialize_schema()
        return repository

    def _build_graph(self) -> GraphCode:
        return GraphBuilder().build_graph(repo_path=str(Path("data/test_repo").resolve()))

    def test_graph_builder_generates_summaries_for_all_objects(self) -> None:
        graph = self._build_graph()

        self.assertTrue(graph.modules)
        self.assertTrue(graph.files)
        self.assertTrue(graph.symbols)
        self.assertTrue(graph.relations)
        self.assertTrue(all(json.loads(module.summary) for module in graph.modules))
        self.assertTrue(all(json.loads(file_obj.summary) for file_obj in graph.files))
        self.assertTrue(all(json.loads(symbol.summary) for symbol in graph.symbols))
        self.assertTrue(all(json.loads(relation.summary) for relation in graph.relations))

    def test_repository_persists_and_updates_summaries(self) -> None:
        repository = self._build_repository()
        graph = self._build_graph()
        repository.save_graphcode(graph)

        module = graph.modules[0]
        stored_summary = repository.get_summary("module", module.id)
        self.assertIsNotNone(stored_summary)
        self.assertEqual(json.loads(stored_summary or "")["module_path"], module.path)

        repository.update_summary("module", module.id, '{"module_path":"override"}')
        self.assertEqual(repository.get_summary("module", module.id), '{"module_path":"override"}')

    def test_summary_api_returns_persisted_summary(self) -> None:
        repository = self._build_repository()
        graph = self._build_graph()
        repository.save_graphcode(graph)
        module = graph.modules[0]

        with patch("app.api.repo.get_graph_repository", return_value=repository):
            client = TestClient(app)
            response = client.get(f"/repo/module/{module.id}/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["object_type"], "module")
        self.assertEqual(payload["object_id"], module.id)
        self.assertEqual(json.loads(payload["summary"])["module_path"], module.path)

    def test_scan_api_builds_and_persists_repository_index(self) -> None:
        repository = self._build_repository()
        repo_path = str(Path("data/test_repo").resolve())

        with patch("app.api.repo.get_graph_repository", return_value=repository):
            client = TestClient(app)
            response = client.post("/repo/scan", json={"repo_path": repo_path, "branch": "main"})

        self.assertEqual(response.status_code, 200)
        payload = RepoBuildResponse.model_validate(response.json())
        self.assertEqual(payload.status, "success")
        self.assertTrue(payload.build_id)
        self.assertTrue(repository.list_modules(payload.build_id))

    def test_scan_api_rejects_missing_repository_path(self) -> None:
        client = TestClient(app)
        response = client.post("/repo/scan", json={"branch": "main"})

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
