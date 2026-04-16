"""Health and readiness endpoint tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.storage.repositories import GraphRepository


class HealthEndpointTests(unittest.TestCase):
    def _repository(self, *, initialized: bool) -> GraphRepository:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        repository = GraphRepository(database_url="sqlite://", engine=engine)
        if initialized:
            repository.initialize_schema()
        return repository

    def test_health_is_lightweight(self) -> None:
        client = TestClient(app)
        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready_reports_ready_when_schema_exists(self) -> None:
        repository = self._repository(initialized=True)
        with patch("app.main.get_graph_repository", return_value=repository):
            client = TestClient(app)
            response = client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["missing_tables"], [])

    def test_ready_reports_missing_schema(self) -> None:
        repository = self._repository(initialized=False)
        with patch("app.main.get_graph_repository", return_value=repository):
            client = TestClient(app)
            response = client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertIn("repos", response.json()["missing_tables"])


if __name__ == "__main__":
    unittest.main()
