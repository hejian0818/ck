"""API authentication tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class ApiAuthTests(unittest.TestCase):
    def test_mutating_endpoint_allows_requests_when_api_key_unset(self) -> None:
        with patch("app.api.dependencies.settings.API_KEY", ""):
            client = TestClient(app)
            response = client.post("/metrics/reset")

        self.assertEqual(response.status_code, 200)

    def test_mutating_endpoint_rejects_missing_api_key_when_configured(self) -> None:
        with patch("app.api.dependencies.settings.API_KEY", "secret"):
            client = TestClient(app)
            response = client.post("/metrics/reset")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "unauthorized")

    def test_mutating_endpoint_accepts_x_api_key(self) -> None:
        with patch("app.api.dependencies.settings.API_KEY", "secret"):
            client = TestClient(app)
            response = client.post("/metrics/reset", headers={"X-API-Key": "secret"})

        self.assertEqual(response.status_code, 200)

    def test_mutating_endpoint_accepts_bearer_token(self) -> None:
        with patch("app.api.dependencies.settings.API_KEY", "secret"):
            client = TestClient(app)
            response = client.post("/metrics/reset", headers={"Authorization": "Bearer secret"})

        self.assertEqual(response.status_code, 200)

    def test_read_endpoint_does_not_require_api_key(self) -> None:
        with patch("app.api.dependencies.settings.API_KEY", "secret"):
            client = TestClient(app)
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
