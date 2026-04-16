"""Repository scanning utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.config import settings


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

    def __init__(self, max_files: int | None = None, max_file_bytes: int | None = None) -> None:
        self.max_files = settings.REPO_SCAN_MAX_FILES if max_files is None else max_files
        self.max_file_bytes = settings.REPO_SCAN_MAX_FILE_BYTES if max_file_bytes is None else max_file_bytes

    def scan_repository(self, repo_path: str) -> list[str]:
        """Return relative source file paths under the repository."""

        root = Path(repo_path).resolve()
        results: list[str] = []

        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if not self._is_supported_path(root, path):
                continue
            results.append(path.relative_to(root).as_posix())
            self._enforce_file_limit(results)

        return sorted(results)

    def scan_changed_files(self, repo_path: str, base_ref: str = "HEAD") -> list[str]:
        """Return supported changed source files relative to the repository root."""

        changed_files, _ = self.inspect_changes(repo_path, base_ref=base_ref)
        return changed_files

    def inspect_changes(self, repo_path: str, base_ref: str = "HEAD") -> tuple[list[str], list[str]]:
        """Return changed and deleted supported source files relative to the repository root."""

        root = Path(repo_path).resolve()
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "diff", "--name-status", base_ref],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            if base_ref != "HEAD":
                try:
                    result = subprocess.run(
                        ["git", "-C", str(root), "diff", "--name-status", "HEAD"],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except (OSError, subprocess.CalledProcessError) as fallback_exc:
                    raise ValueError(f"Failed to inspect changed files from {base_ref}") from fallback_exc
            else:
                raise ValueError(f"Failed to inspect changed files from {base_ref}") from exc

        untracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            text=True,
        )

        changed_files: list[str] = []
        deleted_files: list[str] = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            status, _, relative_path = line.partition("\t")
            relative_path = relative_path.strip()
            if not relative_path:
                continue
            normalized_path = Path(relative_path).as_posix()
            absolute_path = root / normalized_path
            if self._is_supported_path(root, absolute_path, allow_missing=status.startswith("D")):
                if status.startswith("D"):
                    deleted_files.append(normalized_path)
                else:
                    changed_files.append(normalized_path)
                    self._enforce_file_limit(changed_files)

        for raw_path in untracked.stdout.splitlines():
            relative_path = raw_path.strip()
            if not relative_path:
                continue
            absolute_path = root / relative_path
            if self._is_supported_path(root, absolute_path):
                changed_files.append(Path(relative_path).as_posix())
                self._enforce_file_limit(changed_files)
        return sorted(dict.fromkeys(changed_files)), sorted(dict.fromkeys(deleted_files))

    def _is_supported_path(self, root: Path, path: Path, *, allow_missing: bool = False) -> bool:
        if not allow_missing and (not path.exists() or path.is_dir()):
            return False
        if self._is_ignored(root, path):
            return False
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False
        if not allow_missing and self.max_file_bytes > 0 and path.stat().st_size > self.max_file_bytes:
            return False
        if not allow_missing and self._looks_binary(path):
            return False
        return True

    def _enforce_file_limit(self, files: list[str]) -> None:
        if self.max_files > 0 and len(files) > self.max_files:
            raise ValueError(
                f"Repository scan exceeded file limit: {len(files)} files found, max is {self.max_files}"
            )

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
