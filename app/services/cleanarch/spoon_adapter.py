"""Regex-based Spoon adapter fallback for Java parsing."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.graph_objects import Relation, Span, Symbol
from app.services.cleanarch.parser_adapter import ParseResult, ParserAdapter


class SpoonAdapter(ParserAdapter):
    """Parse Java symbols and lightweight relations without invoking Spoon."""

    PACKAGE_PATTERN = re.compile(r"(?:^|\n)\s*package\s+([A-Za-z_$][\w$.]*)\s*;", re.MULTILINE)

    CLASS_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*(?:@\w+(?:\([^)]*\))?\s*)*"
        r"(?:(?:public|private|protected|abstract|static|final|sealed|non-sealed|strictfp)\s+)*"
        r"(class|interface)\s+([A-Za-z_$]\w*)\s*(?:<[^>{;]+>)?([^{;]*)\{",
        re.MULTILINE,
    )
    METHOD_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*(?:@\w+(?:\([^)]*\))?\s*)*"
        r"(?P<mods>(?:(?:public|private|protected|static|final|abstract|synchronized|native|default|strictfp)\s+)*)"
        r"(?:<[^>{;]+>\s*)?"
        r"(?P<return>[A-Za-z_$][\w$<>\[\], ?.&]*\s+)?"
        r"(?P<name>[A-Za-z_$]\w*)\s*\((?P<params>[^;{}()]*(?:\([^)]*\)[^;{}()]*)*)\)"
        r"\s*(?:throws\s+[^{;]+)?\{",
        re.MULTILINE,
    )
    FIELD_PATTERN = re.compile(
        r"(?:^|(?<=\n)|(?<=[{};]))\s*(?:@\w+(?:\([^)]*\))?\s*)*"
        r"(?P<mods>(?:(?:public|private|protected|static|final|transient|volatile)\s+)*)"
        r"(?P<type>[A-Za-z_$][\w$<>\[\], ?.&]*)\s+"
        r"(?P<name>[A-Za-z_$]\w*)\s*(?:=[^;]*)?;",
        re.MULTILINE,
    )
    QUALIFIED_CALL_PATTERN = re.compile(r"\b([A-Za-z_$]\w*)\.([A-Za-z_$]\w*)\s*\(")
    DIRECT_CALL_PATTERN = re.compile(r"\b([A-Za-z_$]\w*)\s*\(")

    def parse_file(self, file_path: str) -> ParseResult:
        source = Path(file_path).read_text(encoding="utf-8")
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        import_aliases = self._parse_import_aliases(source)
        package_name = self._parse_package_name(source)

        class_infos = self._parse_classes(source, symbols, relations, package_name)
        self._parse_members(source, class_infos, symbols, relations)

        return ParseResult(
            symbols=symbols,
            relations=relations,
            spans=self._build_spans(file_path, symbols),
            import_aliases=import_aliases,
        )

    def supports_language(self, language: str) -> bool:
        return language.lower() == "java"

    def _parse_classes(
        self,
        source: str,
        symbols: list[Symbol],
        relations: list[Relation],
        package_name: str,
    ) -> list[dict[str, object]]:
        class_infos: list[dict[str, object]] = []
        for match in self.CLASS_PATTERN.finditer(source):
            open_brace = match.end() - 1
            end_pos = self._find_matching_brace(source, open_brace)
            start_line = self._line_number(source, match.start(2))
            end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
            class_infos.append(
                {
                    "name": match.group(2),
                    "kind": match.group(1),
                    "header": match.group(3),
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
            parents = [
                candidate
                for candidate in class_infos[:index]
                if int(candidate["body_start"]) <= int(info["start"]) <= int(candidate["end"])
            ]
            parent = max(parents, key=lambda item: int(item["start"]), default=None)
            if parent and parent["qualified_name"]:
                qualified_name = f"{parent['qualified_name']}.{info['name']}"
            elif package_name:
                qualified_name = f"{package_name}.{info['name']}"
            else:
                qualified_name = str(info["name"])
            info["qualified_name"] = qualified_name
            symbols.append(
                self._build_symbol(
                    name=str(info["name"]),
                    qualified_name=qualified_name,
                    symbol_type=str(info["kind"]),
                    signature=str(info["signature"]),
                    start_line=int(info["start_line"]),
                    end_line=int(info["end_line"]),
                )
            )
            self._parse_type_relations(str(info["header"]), qualified_name, relations)
        return class_infos

    def _parse_members(
        self,
        source: str,
        class_infos: list[dict[str, object]],
        symbols: list[Symbol],
        relations: list[Relation],
    ) -> None:
        for info in class_infos:
            class_name = str(info["name"])
            class_qualified_name = str(info["qualified_name"])
            body_start = int(info["body_start"])
            body_end = int(info["end"])
            body = source[body_start:body_end]
            child_ranges = [
                (int(candidate["start"]), int(candidate["end"]))
                for candidate in class_infos
                if body_start <= int(candidate["start"]) <= body_end and candidate is not info
            ]

            for match in self.METHOD_PATTERN.finditer(source, body_start, body_end):
                member_start = match.start("name")
                if self._is_nested_member(source, body_start, member_start) or self._position_in_ranges(
                    member_start, child_ranges
                ):
                    continue
                method_name = match.group("name")
                if method_name in self._JAVA_KEYWORDS:
                    continue
                return_type = (match.group("return") or "").strip()
                if not return_type and method_name != class_name:
                    continue
                start_line = self._line_number(source, match.start("name"))
                end_pos = self._find_matching_brace(source, match.end() - 1)
                end_line = self._line_number(source, end_pos) if end_pos is not None else start_line
                qualified_name = f"{class_qualified_name}.{method_name}"
                signature = self._signature_from_match(source, match)
                symbols.append(
                    self._build_symbol(
                        name=method_name,
                        qualified_name=qualified_name,
                        symbol_type="method",
                        signature=signature,
                        start_line=start_line,
                        end_line=end_line,
                        visibility=self._visibility(match.group("mods")),
                    )
                )
                method_body_end = end_pos if end_pos is not None else match.end()
                self._parse_calls(source[match.end() : method_body_end], qualified_name, relations)

            for match in self.FIELD_PATTERN.finditer(body):
                absolute_start = body_start + match.start("name")
                if self._is_nested_member(source, body_start, absolute_start):
                    continue
                field_name = match.group("name")
                if field_name in self._JAVA_KEYWORDS:
                    continue
                start_line = self._line_number(source, body_start + match.start("name"))
                qualified_name = f"{class_qualified_name}.{field_name}"
                symbols.append(
                    self._build_symbol(
                        name=field_name,
                        qualified_name=qualified_name,
                        symbol_type="field",
                        signature=source[body_start + match.start() : body_start + match.end()].strip(),
                        start_line=start_line,
                        end_line=start_line,
                        visibility=self._visibility(match.group("mods")),
                    )
                )

    def _parse_type_relations(self, header: str, qualified_name: str, relations: list[Relation]) -> None:
        extends = re.search(r"\bextends\s+(.+?)(?:\bimplements\b|$)", header)
        if extends:
            for target in self._split_type_list(extends.group(1)):
                relations.append(self._build_relation("inherits", qualified_name, self._clean_type_name(target)))

        implements = re.search(r"\bimplements\s+(.+)$", header)
        if implements:
            for target in self._split_type_list(implements.group(1)):
                relations.append(self._build_relation("implements", qualified_name, self._clean_type_name(target)))

    def _parse_calls(self, body: str, source_id: str, relations: list[Relation]) -> None:
        seen_targets: set[str] = set()
        for match in self.QUALIFIED_CALL_PATTERN.finditer(body):
            target = f"{match.group(1)}.{match.group(2)}"
            if target not in seen_targets:
                relations.append(self._build_relation("calls", source_id, target))
                seen_targets.add(target)
        for match in self.DIRECT_CALL_PATTERN.finditer(body):
            if match.start(1) > 0 and body[match.start(1) - 1] == ".":
                continue
            target = match.group(1)
            if target in self._JAVA_KEYWORDS:
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
    def _visibility(modifiers: str) -> str:
        for visibility in ("public", "private", "protected"):
            if re.search(rf"\b{visibility}\b", modifiers):
                return visibility
        return "package"

    @staticmethod
    def _clean_type_name(type_name: str) -> str:
        return re.sub(r"<.*>", "", type_name).strip().split()[-1]

    @staticmethod
    def _split_type_list(text: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        start = 0
        for index, char in enumerate(text):
            if char == "<":
                depth += 1
            elif char == ">":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
        tail = text[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    @staticmethod
    def _parse_import_aliases(source: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        import_pattern = re.compile(
            r"(?:^|\n)\s*import\s+(?:(static)\s+)?([A-Za-z_$][\w$.\*]+)\s*;",
            re.MULTILINE,
        )
        for match in import_pattern.finditer(source):
            imported = match.group(2).strip()
            if imported.endswith(".*"):
                continue
            local_name = imported.split(".")[-1]
            aliases[local_name] = imported if match.group(1) else local_name
        return aliases

    @staticmethod
    def _parse_package_name(source: str) -> str:
        match = SpoonAdapter.PACKAGE_PATTERN.search(source)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _position_in_ranges(position: int, ranges: list[tuple[int, int]]) -> bool:
        return any(start <= position <= end for start, end in ranges)

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

    _JAVA_KEYWORDS = {
        "catch",
        "do",
        "for",
        "if",
        "new",
        "return",
        "switch",
        "synchronized",
        "try",
        "while",
    }
