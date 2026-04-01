"""Rule-based summary builders for graph objects."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from time import perf_counter

from app.core.logging import get_logger
from app.core.summary_rules import (
    FILE_LANGUAGE_DEFAULTS,
    FILE_RESPONSIBILITY_DEFAULT,
    FILE_RESPONSIBILITY_RULES,
    MODULE_CORE_FILE_LIMIT,
    MODULE_CORE_SYMBOL_LIMIT,
    MODULE_RESPONSIBILITY_DEFAULT,
    MODULE_RESPONSIBILITY_RULES,
    RELATION_LABEL_TEMPLATES,
    SYMBOL_RESPONSIBILITY_RULES,
)
from app.models.graph_objects import File, GraphCode, Module, Relation, Symbol

logger = get_logger(__name__)

_SIGNATURE_RE = re.compile(r"^[^(]+\((?P<params>[^)]*)\)\s*(?:->\s*(?P<return>.+))?$")


class SummaryBuilder(ABC):
    """Unified interface for rule-based summary builders."""

    @abstractmethod
    def build(self, **kwargs: object) -> str:
        """Build a summary string for a graph object."""


class ModuleSummaryBuilder(SummaryBuilder):
    """Build summaries for module objects."""

    def build(
        self,
        *,
        module: Module,
        files: list[File],
        symbols: list[Symbol],
        relations: list[Relation],
    ) -> str:
        summary = {
            "module_path": module.path,
            "responsibility_label": self._infer_responsibility(module),
            "core_files": self._select_core_files(files, symbols),
            "core_symbols": self._select_core_symbols(symbols),
            "adjacent_modules": self._collect_adjacent_modules(module, relations),
        }
        return _dump_summary(summary)

    def _infer_responsibility(self, module: Module) -> str:
        target = f"{module.name}/{module.path}".lower()
        for keyword, label in MODULE_RESPONSIBILITY_RULES:
            if keyword in target:
                return label
        return MODULE_RESPONSIBILITY_DEFAULT

    def _select_core_files(self, files: list[File], symbols: list[Symbol]) -> list[str]:
        symbol_counts = {file_obj.id: 0 for file_obj in files}
        for symbol in symbols:
            if symbol.file_id in symbol_counts:
                symbol_counts[symbol.file_id] += 1

        ranked_files = sorted(
            files,
            key=lambda file_obj: (-symbol_counts[file_obj.id], file_obj.path),
        )
        return [file_obj.path for file_obj in ranked_files[:MODULE_CORE_FILE_LIMIT]]

    def _select_core_symbols(self, symbols: list[Symbol]) -> list[str]:
        public_symbols = [
            symbol.qualified_name
            for symbol in symbols
            if symbol.visibility == "public" and symbol.type.lower() in {"class", "function", "method"}
        ]
        return sorted(public_symbols)[:MODULE_CORE_SYMBOL_LIMIT]

    def _collect_adjacent_modules(self, module: Module, relations: list[Relation]) -> list[str]:
        neighbors: set[str] = set()
        for relation in relations:
            if relation.source_module_id == module.id and relation.target_module_id != module.id:
                neighbors.add(relation.target_module_id)
            if relation.target_module_id == module.id and relation.source_module_id != module.id:
                neighbors.add(relation.source_module_id)
        return sorted(neighbors)


class FileSummaryBuilder(SummaryBuilder):
    """Build summaries for file objects."""

    def build(
        self,
        *,
        file_obj: File,
        module: Module | None,
        symbols: list[Symbol],
        relations: list[Relation],
        object_names: dict[str, str] | None = None,
        object_file_ids: dict[str, str] | None = None,
    ) -> str:
        summary = {
            "file_path": file_obj.path,
            "module": module.path if module else file_obj.module_id,
            "responsibility_label": self._infer_responsibility(file_obj),
            "main_symbols": sorted(symbol.qualified_name for symbol in symbols if symbol.visibility == "public"),
            "dependencies": self._collect_dependencies(file_obj, symbols, relations, object_names, object_file_ids),
        }
        return _dump_summary(summary)

    def _infer_responsibility(self, file_obj: File) -> str:
        name = file_obj.name.lower()
        for keyword, label in FILE_RESPONSIBILITY_RULES:
            if keyword in name:
                return label
        return FILE_LANGUAGE_DEFAULTS.get(file_obj.language.lower(), FILE_RESPONSIBILITY_DEFAULT)

    def _collect_dependencies(
        self,
        file_obj: File,
        symbols: list[Symbol],
        relations: list[Relation],
        object_names: dict[str, str] | None,
        object_file_ids: dict[str, str] | None,
    ) -> list[str]:
        symbol_ids = {symbol.id for symbol in symbols}
        dependencies: set[str] = set()
        for relation in relations:
            if relation.source_id in symbol_ids:
                dependency_id = relation.target_id
            elif relation.target_id in symbol_ids:
                dependency_id = relation.source_id
            else:
                continue

            dependency_file_id = (object_file_ids or {}).get(dependency_id)
            if dependency_file_id and dependency_file_id == file_obj.id:
                continue

            dependencies.add((object_names or {}).get(dependency_id, dependency_id))
        return sorted(dependencies)


class SymbolSummaryBuilder(SummaryBuilder):
    """Build summaries for symbols."""

    def build(
        self,
        *,
        symbol: Symbol,
        relations: list[Relation],
        file_path: str | None = None,
        module_path: str | None = None,
        object_names: dict[str, str] | None = None,
    ) -> str:
        parameters, return_value = self._parse_signature(symbol.signature)
        summary = {
            "name": symbol.name,
            "signature": symbol.signature,
            "file": file_path or symbol.file_id,
            "module": module_path or symbol.module_id,
            "parameters": parameters,
            "return_value": return_value,
            "responsibility_label": self._infer_responsibility(symbol),
            "callers": self._collect_callers(symbol, relations, object_names),
            "callees": self._collect_callees(symbol, relations, object_names),
            "external_dependencies": self._collect_external_dependencies(symbol, relations, object_names),
        }
        return _dump_summary(summary)

    def _parse_signature(self, signature: str) -> tuple[list[str], str | None]:
        match = _SIGNATURE_RE.match(signature.strip())
        if not match:
            return [], None
        raw_params = match.group("params") or ""
        parameters = [part.strip() for part in raw_params.split(",") if part.strip()]
        return_value = match.group("return")
        return parameters, return_value.strip() if return_value else None

    def _infer_responsibility(self, symbol: Symbol) -> str:
        name = symbol.name.lower()
        for keyword, label in SYMBOL_RESPONSIBILITY_RULES:
            if keyword in name:
                return label
        return symbol.type.title()

    def _collect_callers(
        self,
        symbol: Symbol,
        relations: list[Relation],
        object_names: dict[str, str] | None,
    ) -> list[str]:
        callers = {
            (object_names or {}).get(relation.source_id, relation.source_id)
            for relation in relations
            if relation.target_id == symbol.id
        }
        return sorted(callers)

    def _collect_callees(
        self,
        symbol: Symbol,
        relations: list[Relation],
        object_names: dict[str, str] | None,
    ) -> list[str]:
        callees = {
            (object_names or {}).get(relation.target_id, relation.target_id)
            for relation in relations
            if relation.source_id == symbol.id
        }
        return sorted(callees)

    def _collect_external_dependencies(
        self,
        symbol: Symbol,
        relations: list[Relation],
        object_names: dict[str, str] | None,
    ) -> list[str]:
        dependencies: set[str] = set()
        for relation in relations:
            if relation.source_id == symbol.id and relation.target_module_id != symbol.module_id:
                dependencies.add((object_names or {}).get(relation.target_id, relation.target_id))
            elif relation.target_id == symbol.id and relation.source_module_id != symbol.module_id:
                dependencies.add((object_names or {}).get(relation.source_id, relation.source_id))
        return sorted(dependencies)


class RelationSummaryBuilder(SummaryBuilder):
    """Build summaries for relations."""

    def build(
        self,
        *,
        relation: Relation,
        source_name: str,
        source_type: str,
        target_name: str,
        target_type: str,
        source_module: str,
        target_module: str,
    ) -> str:
        template = RELATION_LABEL_TEMPLATES.get(relation.relation_type, "{source} relates to {target}")
        summary = {
            "relation_type": relation.relation_type,
            "source_name": source_name,
            "source_type": source_type,
            "target_name": target_name,
            "target_type": target_type,
            "source_module": source_module,
            "target_module": target_module,
            "relationship_label": template.format(source=source_name, target=target_name),
        }
        return _dump_summary(summary)


class SummaryGenerationService:
    """Generate summaries for all graph objects."""

    def __init__(
        self,
        module_builder: ModuleSummaryBuilder | None = None,
        file_builder: FileSummaryBuilder | None = None,
        symbol_builder: SymbolSummaryBuilder | None = None,
        relation_builder: RelationSummaryBuilder | None = None,
    ) -> None:
        self.module_builder = module_builder or ModuleSummaryBuilder()
        self.file_builder = file_builder or FileSummaryBuilder()
        self.symbol_builder = symbol_builder or SymbolSummaryBuilder()
        self.relation_builder = relation_builder or RelationSummaryBuilder()

    def enrich_graph(self, graph: GraphCode) -> GraphCode:
        start = perf_counter()
        modules_by_id = {module.id: module for module in graph.modules}
        object_names = self._build_object_names(graph)
        object_file_ids = {symbol.id: symbol.file_id for symbol in graph.symbols}
        object_file_ids.update({file_obj.id: file_obj.id for file_obj in graph.files})

        modules = [
            module.model_copy(
                update={
                    "summary": self.module_builder.build(
                        module=module,
                        files=[file_obj for file_obj in graph.files if file_obj.module_id == module.id],
                        symbols=[symbol for symbol in graph.symbols if symbol.module_id == module.id],
                        relations=[
                            relation
                            for relation in graph.relations
                            if relation.source_module_id == module.id or relation.target_module_id == module.id
                        ],
                    )
                }
            )
            for module in graph.modules
        ]

        files = [
            file_obj.model_copy(
                update={
                    "summary": self.file_builder.build(
                        file_obj=file_obj,
                        module=modules_by_id.get(file_obj.module_id),
                        symbols=file_symbols,
                        relations=[
                            relation
                            for relation in graph.relations
                            if relation.source_id in file_symbol_ids or relation.target_id in file_symbol_ids
                        ],
                        object_names=object_names,
                        object_file_ids=object_file_ids,
                    )
                }
            )
            for file_obj in graph.files
            for file_symbols in [[symbol for symbol in graph.symbols if symbol.file_id == file_obj.id]]
            for file_symbol_ids in [{symbol.id for symbol in file_symbols}]
        ]

        file_paths_by_id = {file_obj.id: file_obj.path for file_obj in graph.files}
        module_paths_by_id = {module.id: module.path for module in graph.modules}

        symbols = [
            symbol.model_copy(
                update={
                    "summary": self.symbol_builder.build(
                        symbol=symbol,
                        relations=[
                            relation
                            for relation in graph.relations
                            if relation.source_id == symbol.id or relation.target_id == symbol.id
                        ],
                        file_path=file_paths_by_id.get(symbol.file_id),
                        module_path=module_paths_by_id.get(symbol.module_id),
                        object_names=object_names,
                    )
                }
            )
            for symbol in graph.symbols
        ]

        relations = [
            relation.model_copy(
                update={
                    "summary": self.relation_builder.build(
                        relation=relation,
                        source_name=object_names.get(relation.source_id, relation.source_id),
                        source_type=relation.source_type,
                        target_name=object_names.get(relation.target_id, relation.target_id),
                        target_type=relation.target_type,
                        source_module=module_paths_by_id.get(relation.source_module_id, relation.source_module_id),
                        target_module=module_paths_by_id.get(relation.target_module_id, relation.target_module_id),
                    )
                }
            )
            for relation in graph.relations
        ]

        duration_ms = round((perf_counter() - start) * 1000, 3)
        logger.info(
            "summary_generation_completed",
            extra={
                "context": {
                    "duration_ms": duration_ms,
                    "modules": len(modules),
                    "files": len(files),
                    "symbols": len(symbols),
                    "relations": len(relations),
                }
            },
        )
        return graph.model_copy(
            update={
                "modules": modules,
                "files": files,
                "symbols": symbols,
                "relations": relations,
            }
        )

    def _build_object_names(self, graph: GraphCode) -> dict[str, str]:
        names = {module.id: module.name for module in graph.modules}
        names.update({file_obj.id: file_obj.path for file_obj in graph.files})
        names.update({symbol.id: symbol.qualified_name for symbol in graph.symbols})
        return names


def _dump_summary(summary: dict[str, object]) -> str:
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)
