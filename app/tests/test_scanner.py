"""Scanner tests."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.cleanarch.scanner import RepoScanner


class RepoScannerTests(unittest.TestCase):
    def test_scan_repository_returns_relative_python_files(self) -> None:
        files = RepoScanner().scan_repository("data/test_repo")
        self.assertIn("app_core/utils.py", files)
        self.assertIn("web/api.py", files)
        self.assertNotIn("README.md", files)

    def test_scan_changed_files_returns_supported_changed_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "CK Test"], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "ck@example.com"], check=True, capture_output=True, text=True)
            (repo_path / "main.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
            (repo_path / "README.md").write_text("ignore me\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True, capture_output=True, text=True)

            (repo_path / "main.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
            (repo_path / "README.md").write_text("still ignore me\n", encoding="utf-8")
            (repo_path / "util.js").write_text("export function run() { return 1; }\n", encoding="utf-8")

            files = RepoScanner().scan_changed_files(str(repo_path), base_ref="HEAD")

        self.assertEqual(files, ["main.py", "util.js"])

    def test_inspect_changes_reports_deleted_supported_sources(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            subprocess.run(["git", "-C", str(repo_path), "init"], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "CK Test"], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "ck@example.com"], check=True, capture_output=True, text=True)
            (repo_path / "main.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
            (repo_path / "old.py").write_text("def old():\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo_path), "add", "."], check=True, capture_output=True, text=True)
            subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True, capture_output=True, text=True)

            (repo_path / "main.py").write_text("def helper():\n    return 2\n", encoding="utf-8")
            (repo_path / "old.py").unlink()

            changed, deleted = RepoScanner().inspect_changes(str(repo_path), base_ref="HEAD")

        self.assertEqual(changed, ["main.py"])
        self.assertEqual(deleted, ["old.py"])


if __name__ == "__main__":
    unittest.main()
