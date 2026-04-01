"""Parser adapter selection."""

from __future__ import annotations

from pathlib import Path

from app.services.cleanarch.cdt_adapter import CDTAdapter
from app.services.cleanarch.parser_adapter import ParserAdapter
from app.services.cleanarch.spoon_adapter import SpoonAdapter
from app.services.cleanarch.treesitter_adapter import TreeSitterAdapter


class ParserFactory:
    """Select the correct parser adapter for a file."""

    EXTENSION_LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "javascript",
        ".tsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".hpp": "cpp",
    }

    def __init__(self) -> None:
        self.adapters: list[ParserAdapter] = [
            TreeSitterAdapter(),
            SpoonAdapter(),
            CDTAdapter(),
        ]

    def get_adapter(self, file_path: str) -> ParserAdapter | None:
        language = self.detect_language(file_path)
        for adapter in self.adapters:
            if adapter.supports_language(language):
                return adapter
        return None

    @classmethod
    def detect_language(cls, file_path: str) -> str:
        return cls.EXTENSION_LANGUAGE_MAP.get(Path(file_path).suffix.lower(), "")
