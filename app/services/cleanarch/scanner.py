"""Repository scanning utilities."""

from __future__ import annotations

from pathlib import Path


class RepoScanner:
    """Scan repositories and return supported source files."""

    IGNORED_DIRECTORIES = {
        ".git",
        "node_modules",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".pytest_cache",
        "venv",
        ".venv",
    }

    IGNORED_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".svg",
        ".ico",
        ".mp4",
        ".mov",
        ".avi",
        ".mp3",
        ".wav",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".class",
        ".jar",
        ".so",
        ".dylib",
        ".exe",
    }

    SUPPORTED_EXTENSIONS = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
    }

    def scan_repository(self, repo_path: str) -> list[str]:
        """Return relative source file paths under the repository."""

        root = Path(repo_path).resolve()
        results: list[str] = []

        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if self._is_ignored(root, path):
                continue
            if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
            if self._looks_binary(path):
                continue
            results.append(path.relative_to(root).as_posix())

        return sorted(results)

    def _is_ignored(self, root: Path, path: Path) -> bool:
        relative_parts = path.relative_to(root).parts
        if any(part in self.IGNORED_DIRECTORIES for part in relative_parts[:-1]):
            return True
        if path.suffix.lower() in self.IGNORED_EXTENSIONS:
            return True
        filename = path.name
        if filename.endswith(".min.js") or filename.endswith(".bundle.js"):
            return True
        return False

    @staticmethod
    def _looks_binary(path: Path) -> bool:
        try:
            data = path.read_bytes()[:1024]
        except OSError:
            return True
        return b"\x00" in data
