"""Tree-sitter based adapter with a Python stdlib fallback."""

from __future__ import annotations

import ast
from pathlib import Path

from app.models.graph_objects import Relation, Span, Symbol
from app.services.cleanarch.parser_adapter import ParseResult, ParserAdapter


class _PythonSymbolVisitor(ast.NodeVisitor):
    """Extract symbols and call relations from a Python AST."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.scope_stack: list[str] = []
        self.symbols: list[Symbol] = []
        self.relations: list[Relation] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = ".".join([*self.scope_stack, node.name]) if self.scope_stack else node.name
        self.symbols.append(
            Symbol(
                id="",
                name=node.name,
                qualified_name=qualified_name,
                type="class",
                signature=node.name,
                file_id="",
                module_id="",
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                visibility="public",
                doc=ast.get_docstring(node) or "",
            )
        )
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_like(node)

    def _visit_function_like(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        symbol_type = "method" if self.scope_stack else "function"
        qualified_name = ".".join([*self.scope_stack, node.name]) if self.scope_stack else node.name
        signature = f"{node.name}({', '.join(arg.arg for arg in node.args.args)})"
        self.symbols.append(
            Symbol(
                id="",
                name=node.name,
                qualified_name=qualified_name,
                type=symbol_type,
                signature=signature,
                file_id="",
                module_id="",
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                visibility="private" if node.name.startswith("_") else "public",
                doc=ast.get_docstring(node) or "",
            )
        )
        previous_scope = self.scope_stack.copy()
        self.scope_stack.append(node.name)
        for child in node.body:
            self.visit(child)
        current_symbol = qualified_name
        for nested in ast.walk(node):
            if isinstance(nested, ast.Call):
                callee = self._resolve_call_name(nested.func)
                if not callee:
                    continue
                self.relations.append(
                    Relation(
                        id="",
                        relation_type="calls",
                        source_id=current_symbol,
                        target_id=callee,
                        source_type="symbol",
                        target_type="symbol",
                        source_module_id="",
                        target_module_id="",
                    )
                )
        self.scope_stack = previous_scope

    @staticmethod
    def _resolve_call_name(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts: list[str] = []
            current: ast.AST | None = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts))
        return None


class TreeSitterAdapter(ParserAdapter):
    """Parse Python, JavaScript, Go, and Rust sources."""

    SUPPORTED_LANGUAGES = {"python", "javascript", "go", "rust"}

    def parse_file(self, file_path: str) -> ParseResult:
        language = self._detect_language(file_path)
        if language == "python":
            return self._parse_python(file_path)
        return ParseResult()

    def supports_language(self, language: str) -> bool:
        return language.lower() in self.SUPPORTED_LANGUAGES

    @staticmethod
    def _detect_language(file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "javascript",
            ".tsx": "javascript",
            ".go": "go",
            ".rs": "rust",
        }.get(suffix, "")

    def _parse_python(self, file_path: str) -> ParseResult:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        visitor = _PythonSymbolVisitor(file_path=file_path)
        visitor.visit(tree)

        spans = [
            Span(
                file_path=file_path,
                line_start=symbol.start_line,
                line_end=symbol.end_line,
                module_id="",
                file_id="",
                symbol_id=symbol.qualified_name,
                node_type="symbol",
            )
            for symbol in visitor.symbols
        ]

        return ParseResult(symbols=visitor.symbols, relations=visitor.relations, spans=spans)
