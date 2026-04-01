"""Mock Eclipse CDT adapter for C/C++ parsing."""

from __future__ import annotations

import subprocess

from app.services.cleanarch.parser_adapter import ParseResult, ParserAdapter


class CDTAdapter(ParserAdapter):
    """Placeholder adapter that can be replaced with real CDT integration."""

    def parse_file(self, file_path: str) -> ParseResult:
        _ = subprocess.CompletedProcess(args=["cdt", file_path], returncode=0)
        return ParseResult()

    def supports_language(self, language: str) -> bool:
        return language.lower() in {"c", "c++", "cpp"}
