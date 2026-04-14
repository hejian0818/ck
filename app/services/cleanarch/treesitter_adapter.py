"""Tree-sitter based adapter with a Python stdlib fallback."""

from __future__ import annotations

import ast
import re
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
        self.import_aliases: dict[str, str] = {}

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

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[-1]
            self.import_aliases[local_name] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module_ref = self._python_module_reference(node.module, node.level)
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            imported_name = alias.name.split(".")[-1]
            self.import_aliases[local_name] = f"{module_ref}.{imported_name}" if module_ref else imported_name

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

    def _python_module_reference(self, module_name: str | None, level: int) -> str:
        module_parts = [part for part in (module_name or "").split(".") if part]
        if level <= 0:
            return ".".join(module_parts)

        source_path = Path(self.file_path)
        anchor = source_path.parent
        for _ in range(max(level - 1, 0)):
            anchor = anchor.parent
        if module_parts:
            return ".".join(module_parts)
        return anchor.name


class TreeSitterAdapter(ParserAdapter):
    """Parse Python, JavaScript, Go, and Rust sources."""

    SUPPORTED_LANGUAGES = {"python", "javascript", "go", "rust"}

    def parse_file(self, file_path: str) -> ParseResult:
        language = self._detect_language(file_path)
        if language == "python":
            return self._parse_python(file_path)
        if language == "javascript":
            return self._parse_javascript(file_path)
        if language == "go":
            return self._parse_go(file_path)
        if language == "rust":
            return self._parse_rust(file_path)
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

        return ParseResult(
            symbols=visitor.symbols,
            relations=visitor.relations,
            spans=spans,
            import_aliases=visitor.import_aliases,
        )

    def _parse_javascript(self, file_path: str) -> ParseResult:
        source = Path(file_path).read_text(encoding="utf-8")
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        class_ranges: list[tuple[int, int]] = []
        callable_ranges: list[tuple[str, int, int]] = []

        class_pattern = re.compile(
            r"(?:^|\n)\s*(?:export\s+default\s+|export\s+)?class\s+([A-Za-z_$][\w$]*)[^{]*\{",
            re.MULTILINE,
        )
        for match in class_pattern.finditer(source):
            name = match.group(1)
            start_line = self._line_number(source, match.start(1))
            end_pos = self._find_matching_brace(source, match.end() - 1)
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            class_ranges.append((match.start(), end_pos if end_pos is not None else match.end()))
            symbols.append(
                self._build_symbol(
                    name=name,
                    qualified_name=name,
                    symbol_type="class",
                    signature=self._signature_from_match(source, match),
                    start_line=start_line,
                    end_line=end_line,
                )
            )
            if self._is_exported_prefix(match.group(0)):
                relations.append(self._build_export_relation(name, exported_as=self._export_name(match.group(0), name)))

            body_start = match.end()
            body_end = end_pos if end_pos is not None else match.end()
            method_pattern = re.compile(
                r"(?:^|\n)\s*(?:public\s+|private\s+|protected\s+)?(?:async\s+)?(?:static\s+)?"
                r"(?:(?:get|set)\s+)?(#?[A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::\s*[^{]+)?\{",
                re.MULTILINE,
            )
            for method_match in method_pattern.finditer(source, body_start, body_end):
                if self._brace_delta(source[body_start:method_match.start()]) != 0:
                    continue
                method_name = method_match.group(1).lstrip("#")
                if method_name in {"if", "for", "while", "switch", "catch"}:
                    continue
                method_start_line = self._line_number(source, method_match.start(1))
                method_end_pos = self._find_matching_brace(source, method_match.end() - 1)
                method_end_line = (
                    self._line_number(source, method_end_pos) if method_end_pos is not None else method_start_line
                )
                symbols.append(
                    self._build_symbol(
                        name=method_name,
                        qualified_name=f"{name}.{method_name}",
                        symbol_type="method",
                        signature=f"{method_name}({method_match.group(2).strip()})",
                        start_line=method_start_line,
                        end_line=method_end_line,
                        visibility="private" if method_match.group(1).startswith("#") else "public",
                    )
                )
                callable_ranges.append((f"{name}.{method_name}", method_match.end(), method_end_pos or method_match.end()))

        function_pattern = re.compile(
            r"(?:^|\n)\s*(?:export\s+default\s+|export\s+)?(?:async\s+)?function\s+"
            r"([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::\s*[^{]+)?\{",
            re.MULTILINE,
        )
        for match in function_pattern.finditer(source):
            if self._position_in_ranges(match.start(), class_ranges):
                continue
            name = match.group(1)
            start_line = self._line_number(source, match.start(1))
            end_pos = self._find_matching_brace(source, match.end() - 1)
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            symbols.append(
                self._build_symbol(
                    name=name,
                    qualified_name=name,
                    symbol_type="function",
                    signature=f"{name}({match.group(2).strip()})",
                    start_line=start_line,
                    end_line=end_line,
                )
            )
            if self._is_exported_prefix(match.group(0)):
                relations.append(self._build_export_relation(name, exported_as=self._export_name(match.group(0), name)))
            callable_ranges.append((name, match.end(), end_pos or match.end()))

        arrow_pattern = re.compile(
            r"(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*"
            r"(?::\s*[^=]+)?=\s*(?:async\s+)?(?:\(([^)]*)\)|([A-Za-z_$][\w$]*))\s*=>\s*(\{)?",
            re.MULTILINE,
        )
        for match in arrow_pattern.finditer(source):
            if self._position_in_ranges(match.start(), class_ranges):
                continue
            name = match.group(1)
            params = (match.group(2) or match.group(3) or "").strip()
            start_line = self._line_number(source, match.start(1))
            if match.group(4):
                end_pos = self._find_matching_brace(source, match.end(4) - 1)
                end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            else:
                end_line = start_line
            symbols.append(
                self._build_symbol(
                    name=name,
                    qualified_name=name,
                    symbol_type="function",
                    signature=f"{name}({params})",
                    start_line=start_line,
                    end_line=end_line,
                )
            )
            if self._is_exported_prefix(match.group(0)):
                relations.append(self._build_export_relation(name, exported_as=self._export_name(match.group(0), name)))
            if match.group(4):
                callable_ranges.append((name, match.end(), end_pos or match.end()))

        import_aliases = self._parse_javascript_import_aliases(source, file_path)
        relations.extend(self._parse_named_exports(source, {symbol.name: symbol.qualified_name for symbol in symbols}))
        relations.extend(self._parse_body_calls(source, callable_ranges, self._javascript_call_targets))
        return ParseResult(
            symbols=symbols,
            relations=relations,
            spans=self._build_spans(file_path, symbols),
            import_aliases=import_aliases,
        )

    def _parse_go(self, file_path: str) -> ParseResult:
        source = Path(file_path).read_text(encoding="utf-8")
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        callable_ranges: list[tuple[str, int, int]] = []
        package_name = self._parse_go_package_name(source)

        struct_pattern = re.compile(r"(?:^|\n)\s*type\s+([A-Za-z_]\w*)\s+struct\s*\{", re.MULTILINE)
        for match in struct_pattern.finditer(source):
            name = match.group(1)
            start_line = self._line_number(source, match.start(1))
            end_pos = self._find_matching_brace(source, match.end() - 1)
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            qualified_name = self._scoped_name(package_name, name)
            symbols.append(
                self._build_symbol(
                    name=name,
                    qualified_name=qualified_name,
                    symbol_type="struct",
                    signature=self._signature_from_match(source, match),
                    start_line=start_line,
                    end_line=end_line,
                )
            )

        func_pattern = re.compile(
            r"(?:^|\n)\s*func\s+(?:\(([^)]*)\)\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)"
            r"\s*(?:\([^)]*\)|[A-Za-z_][\w\[\]\*\.]*)?\s*\{",
            re.MULTILINE,
        )
        for match in func_pattern.finditer(source):
            receiver = self._receiver_type(match.group(1) or "")
            name = match.group(2)
            symbol_type = "method" if receiver else "function"
            scoped_receiver = self._scoped_name(package_name, receiver) if receiver else ""
            qualified_name = f"{scoped_receiver}.{name}" if scoped_receiver else self._scoped_name(package_name, name)
            start_line = self._line_number(source, match.start(2))
            end_pos = self._find_matching_brace(source, match.end() - 1)
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            symbols.append(
                self._build_symbol(
                    name=name,
                    qualified_name=qualified_name,
                    symbol_type=symbol_type,
                    signature=self._signature_from_match(source, match),
                    start_line=start_line,
                    end_line=end_line,
                    visibility="public" if name[:1].isupper() else "private",
                )
            )
            callable_ranges.append((qualified_name, match.end(), end_pos or match.end()))

        relations.extend(self._parse_body_calls(source, callable_ranges, self._go_call_targets))
        return ParseResult(
            symbols=symbols,
            relations=relations,
            spans=self._build_spans(file_path, symbols),
            import_aliases=self._parse_go_import_aliases(source),
        )

    def _parse_rust(self, file_path: str) -> ParseResult:
        source = Path(file_path).read_text(encoding="utf-8")
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        impl_ranges: list[tuple[int, int, str]] = []
        callable_ranges: list[tuple[str, int, int]] = []

        struct_pattern = re.compile(r"(?:^|\n)\s*(?:pub\s+)?struct\s+([A-Za-z_]\w*)\b[^{;]*(\{|;)", re.MULTILINE)
        for match in struct_pattern.finditer(source):
            name = match.group(1)
            start_line = self._line_number(source, match.start(1))
            if match.group(2) == "{":
                end_pos = self._find_matching_brace(source, match.end(2) - 1)
                end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            else:
                end_line = start_line
            symbols.append(
                self._build_symbol(
                    name=name,
                    qualified_name=name,
                    symbol_type="struct",
                    signature=self._signature_from_match(source, match),
                    start_line=start_line,
                    end_line=end_line,
                    visibility="public" if match.group(0).lstrip().startswith("pub ") else "private",
                )
            )

        impl_pattern = re.compile(r"(?:^|\n)\s*impl(?:\s*<[^>]+>)?(?:\s+[^{]+?\s+for)?\s+([A-Za-z_]\w*)[^{]*\{", re.MULTILINE)
        for match in impl_pattern.finditer(source):
            end_pos = self._find_matching_brace(source, match.end() - 1)
            impl_ranges.append((match.start(), end_pos if end_pos is not None else match.end(), match.group(1)))

        fn_pattern = re.compile(
            r"(?:^|(?<=\n)|(?<=[{;]))\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*"
            r"(?:<[^>]+>)?\s*\(([^)]*)\)[^{;]*\{",
            re.MULTILINE,
        )
        for match in fn_pattern.finditer(source):
            impl_name = self._impl_name_for_position(match.start(), impl_ranges)
            name = match.group(1)
            symbol_type = "method" if impl_name else "function"
            qualified_name = f"{impl_name}.{name}" if impl_name else name
            start_line = self._line_number(source, match.start(1))
            end_pos = self._find_matching_brace(source, match.end() - 1)
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            symbols.append(
                self._build_symbol(
                    name=name,
                    qualified_name=qualified_name,
                    symbol_type=symbol_type,
                    signature=self._signature_from_match(source, match),
                    start_line=start_line,
                    end_line=end_line,
                    visibility="public" if match.group(0).lstrip().startswith("pub") else "private",
                )
            )
            callable_ranges.append((qualified_name, match.end(), end_pos or match.end()))

        relations.extend(self._parse_body_calls(source, callable_ranges, self._rust_call_targets))
        return ParseResult(
            symbols=symbols,
            relations=relations,
            spans=self._build_spans(file_path, symbols),
            import_aliases=self._parse_rust_import_aliases(source),
        )

    @staticmethod
    def _build_symbol(
        *,
        name: str,
        qualified_name: str,
        symbol_type: str,
        signature: str,
        start_line: int,
        end_line: int,
        visibility: str = "public",
    ) -> Symbol:
        return Symbol(
            id="",
            name=name,
            qualified_name=qualified_name,
            type=symbol_type,
            signature=signature,
            file_id="",
            module_id="",
            start_line=start_line,
            end_line=end_line,
            visibility=visibility,
            doc="",
        )

    @staticmethod
    def _build_spans(file_path: str, symbols: list[Symbol]) -> list[Span]:
        return [
            Span(
                file_path=file_path,
                line_start=symbol.start_line,
                line_end=symbol.end_line,
                module_id="",
                file_id="",
                symbol_id=symbol.qualified_name,
                node_type="symbol",
            )
            for symbol in symbols
        ]

    @staticmethod
    def _build_export_relation(qualified_name: str, exported_as: str | None = None) -> Relation:
        return Relation(
            id="",
            relation_type="exports",
            source_id=qualified_name,
            target_id=f"export:{exported_as or qualified_name}",
            source_type="symbol",
            target_type="external",
            source_module_id="",
            target_module_id="",
        )

    @staticmethod
    def _line_number(source: str, index: int) -> int:
        return source.count("\n", 0, index) + 1

    @staticmethod
    def _signature_from_match(source: str, match: re.Match[str]) -> str:
        line_start = source.rfind("\n", 0, match.start()) + 1
        line_end = source.find("\n", match.start())
        if line_end == -1:
            line_end = len(source)
        return source[line_start:line_end].strip()

    @staticmethod
    def _position_in_ranges(position: int, ranges: list[tuple[int, int]]) -> bool:
        return any(start <= position <= end for start, end in ranges)

    @staticmethod
    def _impl_name_for_position(position: int, ranges: list[tuple[int, int, str]]) -> str | None:
        for start, end, name in ranges:
            if start <= position <= end:
                return name
        return None

    @staticmethod
    def _is_exported_prefix(text: str) -> bool:
        return bool(re.search(r"(^|\n)\s*export\b", text))

    @staticmethod
    def _export_name(text: str, qualified_name: str) -> str:
        return "default" if re.search(r"(^|\n)\s*export\s+default\b", text) else qualified_name

    def _parse_named_exports(self, source: str, symbol_names: dict[str, str]) -> list[Relation]:
        relations: list[Relation] = []
        export_pattern = re.compile(r"(?:^|\n)\s*export\s*\{([^}]+)\}", re.MULTILINE)
        for match in export_pattern.finditer(source):
            for raw_name in match.group(1).split(","):
                name = raw_name.strip().split(" as ", 1)[0].strip()
                if not name:
                    continue
                relations.append(self._build_export_relation(symbol_names.get(name, name)))
        return relations

    @staticmethod
    def _parse_javascript_import_aliases(source: str, file_path: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        import_pattern = re.compile(r"(?:^|\n)\s*import\s+(.+?)\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
        for match in import_pattern.finditer(source):
            clause = match.group(1).strip()
            module_ref = TreeSitterAdapter._module_reference(file_path, match.group(2).strip())
            default_import, remainder = TreeSitterAdapter._split_javascript_import_clause(clause)
            if default_import:
                aliases[default_import] = f"{module_ref}.default" if module_ref else default_import
            if remainder.startswith("{") and remainder.endswith("}"):
                for item in remainder.strip("{} ").split(","):
                    item = item.strip()
                    if not item:
                        continue
                    imported, _, local = item.partition(" as ")
                    imported_name = imported.strip().split(".")[-1]
                    aliases[(local or imported).strip()] = (
                        f"{module_ref}.{imported_name}" if module_ref else imported_name
                    )
            elif remainder.startswith("* as "):
                alias = remainder.replace("* as ", "", 1).strip()
                aliases[alias] = module_ref or alias
        return aliases

    @staticmethod
    def _split_javascript_import_clause(clause: str) -> tuple[str | None, str]:
        if clause.startswith("{") or clause.startswith("* as "):
            return None, clause
        if "," not in clause:
            return clause.strip(), ""
        default_import, remainder = clause.split(",", 1)
        return default_import.strip(), remainder.strip()

    @staticmethod
    def _parse_go_import_aliases(source: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        block_pattern = re.compile(r"(?:^|\n)\s*import\s*\((.*?)\)", re.MULTILINE | re.DOTALL)
        single_pattern = re.compile(r"(?:^|\n)\s*import\s+([A-Za-z_]\w*)?\s*\"([^\"]+)\"", re.MULTILINE)
        for match in block_pattern.finditer(source):
            for line in match.group(1).splitlines():
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                alias_match = re.match(r'([A-Za-z_]\w*)?\s*"([^"]+)"', line)
                if not alias_match:
                    continue
                alias = alias_match.group(1) or alias_match.group(2).split("/")[-1]
                aliases[alias] = alias_match.group(2).split("/")[-1]
        for match in single_pattern.finditer(source):
            alias = match.group(1) or match.group(2).split("/")[-1]
            aliases[alias] = match.group(2).split("/")[-1]
        return aliases

    @staticmethod
    def _parse_go_package_name(source: str) -> str:
        match = re.search(r"(?:^|\n)\s*package\s+([A-Za-z_]\w*)\b", source, re.MULTILINE)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_rust_import_aliases(source: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        use_pattern = re.compile(r"(?:^|\n)\s*use\s+([^;]+);", re.MULTILINE)
        for match in use_pattern.finditer(source):
            statement = match.group(1).strip()
            if "{" in statement and "}" in statement:
                prefix, _, rest = statement.partition("{")
                prefix = prefix.rstrip(":").strip()
                for item in rest.rstrip("}").split(","):
                    item = item.strip()
                    if not item:
                        continue
                    imported, _, local = item.partition(" as ")
                    imported_path = f"{prefix}::{imported.strip()}" if prefix else imported.strip()
                    leaf = imported_path.split("::")[-1].strip()
                    aliases[(local or leaf).strip()] = TreeSitterAdapter._normalize_rust_import_path(imported_path)
                continue
            imported, _, local = statement.partition(" as ")
            imported_path = imported.strip()
            leaf = imported_path.split("::")[-1].strip()
            aliases[(local or leaf).strip()] = TreeSitterAdapter._normalize_rust_import_path(imported_path)
        return aliases

    @staticmethod
    def _normalize_rust_import_path(imported_path: str) -> str:
        normalized = imported_path.strip()
        for prefix in ("crate::", "self::", "super::"):
            if normalized.startswith(prefix):
                return normalized[len(prefix) :]
        return normalized

    @staticmethod
    def _module_reference(file_path: str, import_path: str) -> str:
        if not import_path.startswith("."):
            return import_path.split("/")[-1]

        source_path = Path(file_path)
        module_path = (source_path.parent / import_path).resolve()
        if module_path.suffix:
            return module_path.stem
        return module_path.name

    def _parse_body_calls(
        self,
        source: str,
        callable_ranges: list[tuple[str, int, int]],
        target_builder: object,
    ) -> list[Relation]:
        relations: list[Relation] = []
        for source_id, body_start, body_end in callable_ranges:
            body = source[body_start:body_end]
            for target_id in target_builder(body):
                if not target_id or target_id == source_id:
                    continue
                relations.append(
                    Relation(
                        id="",
                        relation_type="calls",
                        source_id=source_id,
                        target_id=target_id,
                        source_type="symbol",
                        target_type="symbol",
                        source_module_id="",
                        target_module_id="",
                    )
                )
        return relations

    @staticmethod
    def _javascript_call_targets(body: str) -> list[str]:
        call_pattern = re.compile(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(")
        keywords = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "new"}
        targets: list[str] = []
        for match in call_pattern.finditer(body):
            target = match.group(1)
            short_name = target.split(".")[-1]
            if short_name in keywords:
                continue
            targets.append(target)
        return targets

    @staticmethod
    def _go_call_targets(body: str) -> list[str]:
        call_pattern = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(")
        keywords = {"if", "for", "switch", "return", "func", "make", "new", "defer", "go"}
        targets: list[str] = []
        for match in call_pattern.finditer(body):
            target = match.group(1)
            short_name = target.split(".")[-1]
            if short_name in keywords:
                continue
            targets.append(target)
        return targets

    @staticmethod
    def _rust_call_targets(body: str) -> list[str]:
        call_pattern = re.compile(r"\b([A-Za-z_]\w*(?:(?:::|\.))[A-Za-z_]\w*|[A-Za-z_]\w*)\s*!\s*?\(|\b([A-Za-z_]\w*(?:(?:::|\.))[A-Za-z_]\w*|[A-Za-z_]\w*)\s*\(")
        keywords = {"if", "for", "while", "loop", "match", "return", "Some", "Ok", "Err"}
        targets: list[str] = []
        for match in call_pattern.finditer(body):
            target = match.group(1) or match.group(2) or ""
            target = target.rstrip("!")
            short_name = re.split(r"::|\.", target)[-1]
            if short_name in keywords:
                continue
            targets.append(target)
        return targets

    @staticmethod
    def _receiver_type(receiver: str) -> str:
        parts = receiver.strip().split()
        if not parts:
            return ""
        return parts[-1].lstrip("*")

    @staticmethod
    def _scoped_name(scope: str, name: str) -> str:
        if not scope:
            return name
        if not name:
            return scope
        if name.startswith(f"{scope}."):
            return name
        return f"{scope}.{name}"

    @staticmethod
    def _find_matching_brace(source: str, open_brace_index: int) -> int | None:
        depth = 0
        quote: str | None = None
        escaped = False
        in_line_comment = False
        in_block_comment = False

        index = open_brace_index
        while index < len(source):
            char = source[index]
            next_char = source[index + 1] if index + 1 < len(source) else ""

            if in_line_comment:
                if char == "\n":
                    in_line_comment = False
                index += 1
                continue

            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    index += 2
                else:
                    index += 1
                continue

            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue

            if char == "/" and next_char == "/":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue
            if char in {"'", '"', "`"}:
                quote = char
                index += 1
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None

    @staticmethod
    def _brace_delta(source: str) -> int:
        depth = 0
        quote: str | None = None
        escaped = False
        in_line_comment = False
        in_block_comment = False

        index = 0
        while index < len(source):
            char = source[index]
            next_char = source[index + 1] if index + 1 < len(source) else ""

            if in_line_comment:
                if char == "\n":
                    in_line_comment = False
                index += 1
                continue
            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    index += 2
                else:
                    index += 1
                continue
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue

            if char == "/" and next_char == "/":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue
            if char in {"'", '"', "`"}:
                quote = char
                index += 1
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        return depth
