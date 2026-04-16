"""Regex-based Eclipse CDT adapter fallback for C/C++ parsing."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.graph_objects import Relation, Span, Symbol
from app.services.cleanarch.parser_adapter import ParserAdapter, ParseResult


class CDTAdapter(ParserAdapter):
    """Parse C/C++ symbols and lightweight relations without invoking CDT."""

    INCLUDE_PATTERN = re.compile(r"^\s*#\s*include\s+[<\"]([^>\"]+)[>\"]", re.MULTILINE)
    NAMESPACE_PATTERN = re.compile(r"(?:^|(?<=\n)|(?<=[{};]))\s*namespace\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\{", re.MULTILINE)
    NAMESPACE_ALIAS_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*namespace\s+([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*;",
        re.MULTILINE,
    )
    USING_DECLARATION_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*using\s+([A-Za-z_]\w*(?:::[A-Za-z_]\w*)+)\s*;",
        re.MULTILINE,
    )
    USING_ALIAS_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*using\s+([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*(?:::[A-Za-z_]\w*)+)\s*;",
        re.MULTILINE,
    )
    CLASS_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*(?:template\s*<[^;{}]+>\s*)?"
        r"(class|struct)\s+([A-Za-z_]\w*)\s*(?: final)?(?:\s*:[^{;]+)?\s*\{",
        re.MULTILINE,
    )
    FUNCTION_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*(?:template\s*<[^;{}]+>\s*)?"
        r"(?P<prefix>(?:(?:inline|static|virtual|constexpr|consteval|constinit|extern|friend|explicit)\s+)*)"
        r"(?P<return>[A-Za-z_~][\w:<>*&,\s\[\]]*?\s+)?"
        r"(?P<name>[A-Za-z_~]\w*(?:::[A-Za-z_~]\w*)*)\s*\((?P<params>[^;{}()]*(?:\([^)]*\)[^;{}()]*)*)\)"
        r"\s*(?:const\s*)?(?:noexcept\s*)?(?:override\s*)?(?:final\s*)?(?:->\s*[^{;]+)?\{",
        re.MULTILINE,
    )
    QUALIFIED_CALL_PATTERN = re.compile(r"\b([A-Za-z_]\w*(?:(?:\.|->|::)[A-Za-z_]\w*)+)\s*\(")
    DIRECT_CALL_PATTERN = re.compile(r"\b([A-Za-z_~]\w*)\s*\(")

    def parse_file(self, file_path: str) -> ParseResult:
        source = Path(file_path).read_text(encoding="utf-8")
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        import_aliases = self._parse_import_aliases(source)

        namespace_infos = self._parse_namespaces(source)
        class_infos = self._parse_classes(source, namespace_infos, symbols)
        self._parse_includes(file_path, source, relations)
        self._parse_functions(source, namespace_infos, class_infos, symbols, relations)

        return ParseResult(
            symbols=symbols,
            relations=relations,
            spans=self._build_spans(file_path, symbols),
            import_aliases=import_aliases,
        )

    def supports_language(self, language: str) -> bool:
        return language.lower() in {"c", "c++", "cpp"}

    def _parse_namespaces(self, source: str) -> list[dict[str, object]]:
        namespace_infos: list[dict[str, object]] = []
        for match in self.NAMESPACE_PATTERN.finditer(source):
            end_pos = self._find_matching_brace(source, match.end() - 1)
            namespace_infos.append(
                {
                    "name": match.group(1),
                    "start": match.start(1),
                    "body_start": match.end(),
                    "end": end_pos if end_pos is not None else match.end(),
                    "qualified_name": "",
                }
            )

        namespace_infos.sort(key=lambda item: int(item["start"]))
        for index, info in enumerate(namespace_infos):
            parents = [
                candidate
                for candidate in namespace_infos[:index]
                if int(candidate["body_start"]) <= int(info["start"]) <= int(candidate["end"])
            ]
            parent = max(parents, key=lambda item: int(item["start"]), default=None)
            info["qualified_name"] = (
                f"{parent['qualified_name']}::{info['name']}" if parent and parent["qualified_name"] else info["name"]
            )
        return namespace_infos

    def _parse_classes(
        self,
        source: str,
        namespace_infos: list[dict[str, object]],
        symbols: list[Symbol],
    ) -> list[dict[str, object]]:
        class_infos: list[dict[str, object]] = []
        for match in self.CLASS_PATTERN.finditer(source):
            end_pos = self._find_matching_brace(source, match.end() - 1)
            start_line = self._line_number(source, match.start(2))
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            class_infos.append(
                {
                    "kind": match.group(1),
                    "name": match.group(2),
                    "start": match.start(2),
                    "body_start": match.end(),
                    "end": end_pos if end_pos is not None else match.end(),
                    "start_line": start_line,
                    "end_line": end_line,
                    "signature": self._signature_from_match(source, match),
                    "qualified_name": "",
                }
            )

        class_infos.sort(key=lambda item: int(item["start"]))
        for index, info in enumerate(class_infos):
            class_parents = [
                candidate
                for candidate in class_infos[:index]
                if int(candidate["body_start"]) <= int(info["start"]) <= int(candidate["end"])
            ]
            class_parent = max(class_parents, key=lambda item: int(item["start"]), default=None)
            if class_parent and class_parent["qualified_name"]:
                qualified_name = f"{class_parent['qualified_name']}::{info['name']}"
            else:
                namespace = self._scope_for_position(int(info["start"]), namespace_infos)
                qualified_name = f"{namespace}::{info['name']}" if namespace else str(info["name"])
            info["qualified_name"] = qualified_name
            symbols.append(
                self._build_symbol(
                    name=str(info["name"]),
                    qualified_name=qualified_name,
                    symbol_type=str(info["kind"]),
                    signature=str(info["signature"]),
                    start_line=int(info["start_line"]),
                    end_line=int(info["end_line"]),
                    visibility="public" if info["kind"] == "struct" else "private",
                )
            )
        return class_infos

    def _parse_includes(self, file_path: str, source: str, relations: list[Relation]) -> None:
        for match in self.INCLUDE_PATTERN.finditer(source):
            relations.append(
                Relation(
                    id="",
                    relation_type="depends_on",
                    source_id=file_path,
                    target_id=match.group(1),
                    source_type="file",
                    target_type="external",
                    source_module_id="",
                    target_module_id="",
                )
            )

    @classmethod
    def _parse_import_aliases(cls, source: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for match in cls.NAMESPACE_ALIAS_PATTERN.finditer(source):
            aliases[match.group(1)] = match.group(2)
        for match in cls.USING_DECLARATION_PATTERN.finditer(source):
            target = match.group(1)
            aliases[target.split("::")[-1]] = target
        for match in cls.USING_ALIAS_PATTERN.finditer(source):
            aliases[match.group(1)] = match.group(2)
        return aliases

    def _parse_functions(
        self,
        source: str,
        namespace_infos: list[dict[str, object]],
        class_infos: list[dict[str, object]],
        symbols: list[Symbol],
        relations: list[Relation],
    ) -> None:
        for match in self.FUNCTION_PATTERN.finditer(source):
            function_start = match.start("name")
            raw_name = match.group("name")
            short_name = raw_name.split("::")[-1].lstrip("~")
            if short_name in self._C_CPP_KEYWORDS:
                continue

            containing_class = self._class_for_position(function_start, class_infos)
            scoped_class = self._class_for_qualified_name(raw_name, class_infos)
            in_class_body = containing_class is not None
            if in_class_body and self._is_nested_member(source, int(containing_class["body_start"]), function_start):
                continue

            return_type = (match.group("return") or "").strip()
            is_constructor = bool((containing_class and short_name == containing_class["name"]) or raw_name.split("::")[-1].lstrip("~") in self._class_names(class_infos))
            if not return_type and not is_constructor:
                continue

            start_line = self._line_number(source, match.start("name"))
            end_pos = self._find_matching_brace(source, match.end() - 1)
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line

            if "::" in raw_name:
                qualified_name = self._qualify_scoped_function(raw_name, namespace_infos, scoped_class)
                symbol_type = "method" if scoped_class or len(raw_name.split("::")) > 1 else "function"
            elif containing_class:
                qualified_name = f"{containing_class['qualified_name']}::{raw_name}"
                symbol_type = "method"
            else:
                namespace = self._scope_for_position(function_start, namespace_infos)
                qualified_name = f"{namespace}::{raw_name}" if namespace else raw_name
                symbol_type = "function"

            symbols.append(
                self._build_symbol(
                    name=raw_name.split("::")[-1],
                    qualified_name=qualified_name,
                    symbol_type=symbol_type,
                    signature=self._signature_from_match(source, match),
                    start_line=start_line,
                    end_line=end_line,
                    visibility="public",
                )
            )
            body_end = end_pos if end_pos is not None else match.end()
            self._parse_calls(source[match.end() : body_end], qualified_name, relations)

    def _parse_calls(self, body: str, source_id: str, relations: list[Relation]) -> None:
        seen_targets: set[str] = set()
        for match in self.QUALIFIED_CALL_PATTERN.finditer(body):
            target = match.group(1).replace("->", "::").replace(".", "::")
            short_target = target.split("::")[-1]
            if short_target in self._C_CPP_KEYWORDS:
                continue
            if target not in seen_targets:
                relations.append(self._build_relation("calls", source_id, target))
                seen_targets.add(target)
        for match in self.DIRECT_CALL_PATTERN.finditer(body):
            prefix = body[max(0, match.start(1) - 2) : match.start(1)]
            if prefix.endswith(("::", "->")) or prefix.endswith("."):
                continue
            target = match.group(1)
            if target in self._C_CPP_KEYWORDS:
                continue
            if target not in seen_targets:
                relations.append(self._build_relation("calls", source_id, target))
                seen_targets.add(target)

    @staticmethod
    def _build_symbol(
        *,
        name: str,
        qualified_name: str,
        symbol_type: str,
        signature: str,
        start_line: int,
        end_line: int,
        visibility: str,
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
    def _build_relation(relation_type: str, source_id: str, target_id: str) -> Relation:
        return Relation(
            id="",
            relation_type=relation_type,
            source_id=source_id,
            target_id=target_id,
            source_type="symbol",
            target_type="symbol",
            source_module_id="",
            target_module_id="",
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
    def _scope_for_position(position: int, scopes: list[dict[str, object]]) -> str:
        containing = [
            scope
            for scope in scopes
            if int(scope["body_start"]) <= position <= int(scope["end"]) and scope["qualified_name"]
        ]
        scope = max(containing, key=lambda item: int(item["start"]), default=None)
        return str(scope["qualified_name"]) if scope else ""

    @staticmethod
    def _class_for_position(position: int, class_infos: list[dict[str, object]]) -> dict[str, object] | None:
        containing = [
            info for info in class_infos if int(info["body_start"]) <= position <= int(info["end"])
        ]
        return max(containing, key=lambda item: int(item["start"]), default=None)

    @staticmethod
    def _class_names(class_infos: list[dict[str, object]]) -> set[str]:
        return {str(info["name"]) for info in class_infos}

    @staticmethod
    def _class_for_qualified_name(raw_name: str, class_infos: list[dict[str, object]]) -> dict[str, object] | None:
        if "::" not in raw_name:
            return None
        owner = "::".join(raw_name.split("::")[:-1])
        candidates = [
            info
            for info in class_infos
            if str(info["qualified_name"]).endswith(f"::{owner}") or str(info["qualified_name"]) == owner
        ]
        return max(candidates, key=lambda item: len(str(item["qualified_name"])), default=None)

    @staticmethod
    def _qualify_scoped_function(
        raw_name: str,
        namespace_infos: list[dict[str, object]],
        scoped_class: dict[str, object] | None,
    ) -> str:
        if scoped_class:
            return f"{scoped_class['qualified_name']}::{raw_name.split('::')[-1]}"
        owner = "::".join(raw_name.split("::")[:-1])
        namespace = next(
            (
                str(info["qualified_name"])
                for info in namespace_infos
                if str(info["qualified_name"]).endswith(f"::{owner}") or str(info["qualified_name"]) == owner
            ),
            "",
        )
        return f"{namespace}::{raw_name.split('::')[-1]}" if namespace else raw_name

    def _is_nested_member(self, source: str, body_start: int, member_start: int) -> bool:
        return self._brace_delta(source[body_start:member_start]) != 0

    @staticmethod
    def _brace_delta(text: str) -> int:
        depth = 0
        quote: str | None = None
        escaped = False
        in_line_comment = False
        in_block_comment = False
        for index, char in enumerate(text):
            next_char = text[index + 1] if index + 1 < len(text) else ""
            if in_line_comment:
                if char == "\n":
                    in_line_comment = False
                continue
            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                continue
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char == "/" and next_char == "/":
                in_line_comment = True
            elif char == "/" and next_char == "*":
                in_block_comment = True
            elif char in {"'", '"'}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
        return depth

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
            if char in {"'", '"'}:
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

    _C_CPP_KEYWORDS = {
        "catch",
        "delete",
        "do",
        "for",
        "if",
        "new",
        "return",
        "sizeof",
        "switch",
        "while",
    }
