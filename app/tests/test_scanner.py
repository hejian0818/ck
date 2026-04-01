"""Scanner tests."""

from __future__ import annotations

import unittest

from app.services.cleanarch.scanner import RepoScanner


class RepoScannerTests(unittest.TestCase):
    def test_scan_repository_returns_relative_python_files(self) -> None:
        files = RepoScanner().scan_repository("data/test_repo")
        self.assertIn("app_core/utils.py", files)
        self.assertIn("web/api.py", files)
        self.assertNotIn("README.md", files)


if __name__ == "__main__":
    unittest.main()
