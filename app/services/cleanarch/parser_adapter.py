"""Parser adapter abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.models.graph_objects import Relation, Span, Symbol


class ParseResult(BaseModel):
    """Normalized parser output."""

    symbols: list[Symbol] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
    import_aliases: dict[str, str] = Field(default_factory=dict)


class ParserAdapter(ABC):
    """Common interface for language-specific parsers."""

    @abstractmethod
    def parse_file(self, file_path: str) -> ParseResult:
        """Parse a single file and extract symbols, relations, and spans."""

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """Return whether the adapter supports the given language."""
