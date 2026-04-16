"""Repository graph builder."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from app.core.logging import get_logger
from app.models.graph_objects import File, GraphCode, Module, Relation, RepoMeta, Span, Symbol
from app.services.cleanarch.parser_factory import ParserFactory
from app.services.cleanarch.scanner import RepoScanner
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.indexing.summary_builder import SummaryGenerationService
from app.storage.vector_store import VectorStore

logger = get_logger(__name__)


class GraphBuilder:
    """Build GraphCode from a repository."""

    def __init__(
        self,
        scanner: RepoScanner | None = None,
        parser_factory: ParserFactory | None = None,
        summary_service: SummaryGenerationService | None = None,
        embedding_builder: EmbeddingBuilder | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.scanner = scanner or RepoScanner()
        self.parser_factory = parser_factory or ParserFactory()
        self.summary_service = summary_service or SummaryGenerationService()
        self.embedding_builder = embedding_builder
        self.vector_store = vector_store
        self.last_build_stats = {
            "incremental": False,
            "parsed_files": 0,
            "reused_files": 0,
            "deleted_files": 0,
        }

    def build_graph(
        self,
        repo_path: str,
        branch: str = "main",
        previous_graph: GraphCode | None = None,
        file_paths: list[str] | None = None,
        deleted_paths: list[str] | None = None,
    ) -> GraphCode:
        """Build a graph representation from a repository."""

        root = Path(repo_path).resolve()
        if file_paths is None:
            scanned_file_paths = self.scanner.scan_repository(str(root))
        else:
            scanned_file_paths = file_paths
        scanned_file_paths = sorted(dict.fromkeys(scanned_file_paths))
        partial_rebuild = file_paths is not None
        deleted_path_set = set(deleted_paths or [])
        if partial_rebuild and previous_graph is not None:
            previous_file_paths = {file_obj.path for file_obj in previous_graph.files}
            file_paths = sorted((previous_file_paths | set(scanned_file_paths)) - deleted_path_set)
        else:
            file_paths = scanned_file_paths
        module_map: dict[str, Module] = {}
        files: list[File] = []
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        spans: list[Span] = []
        export_lookup_specs: list[tuple[str, str, dict[str, str], dict[str, str]]] = []
        reused_relations: list[Relation] = []
        previous_files = {file_obj.path: file_obj for file_obj in previous_graph.files} if previous_graph else {}
        previous_symbols_by_file: dict[str, list[Symbol]] = {}
        previous_spans_by_file: dict[str, list[Span]] = {}
        previous_relations_by_file: dict[str, list[Relation]] = {}
        if previous_graph is not None:
            previous_symbols_by_file = self._group_symbols_by_file(previous_graph.symbols)
            previous_spans_by_file = self._group_spans_by_file(previous_graph.spans)
            previous_relations_by_file = self._group_relations_by_file(previous_graph.relations, previous_graph.symbols)
        previous_file_paths = set(previous_files)
        current_file_paths = set(file_paths)
        scanned_file_path_set = set(scanned_file_paths)
        self.last_build_stats = {
            "incremental": previous_graph is not None,
            "parsed_files": 0,
            "reused_files": 0,
            "deleted_files": len((previous_file_paths - current_file_paths) | deleted_path_set),
            "scanned_files": len(scanned_file_path_set - deleted_path_set),
        }

        pending_relations: list[tuple[Relation, str, str, str, dict[str, str], dict[str, str]]] = []

        for index, relative_path in enumerate(file_paths, start=1):
            absolute_path = root / relative_path
            module_name, module_path = self._infer_module(relative_path, root.name)
            module = module_map.setdefault(
                module_name,
                Module(
                    id=f"M_{module_name}",
                    name=module_name,
                    path=module_path,
                    metadata={},
                ),
            )
            previous_file = previous_files.get(relative_path)
            if partial_rebuild and relative_path not in scanned_file_path_set and previous_file is not None:
                files.append(previous_file)
                symbols.extend(previous_symbols_by_file.get(previous_file.id, []))
                spans.extend(previous_spans_by_file.get(previous_file.id, []))
                reused_relations.extend(previous_relations_by_file.get(previous_file.id, []))
                self.last_build_stats["reused_files"] += 1
                continue

            content_hash = self._hash_file(absolute_path)
            language = self.parser_factory.detect_language(relative_path)
            line_count = self._count_lines(absolute_path)
            file_id = self._build_file_id(relative_path)
            file_obj = File(
                id=file_id,
                name=absolute_path.name,
                path=relative_path,
                module_id=module.id,
                language=language,
                content_hash=content_hash,
                start_line=1,
                end_line=line_count,
            )
            if previous_file is not None and previous_file.content_hash == content_hash:
                files.append(file_obj.model_copy(update={"summary": previous_file.summary}))
                spans.append(
                    Span(
                        file_path=relative_path,
                        line_start=1,
                        line_end=line_count,
                        module_id=module.id,
                        file_id=file_id,
                        symbol_id=None,
                        node_type="file",
                    )
                )
                symbols.extend(previous_symbols_by_file.get(previous_file.id, []))
                spans.extend(previous_spans_by_file.get(previous_file.id, []))
                reused_relations.extend(previous_relations_by_file.get(previous_file.id, []))
                self.last_build_stats["reused_files"] += 1
                continue

            self.last_build_stats["parsed_files"] += 1
            files.append(file_obj)
            spans.append(
                Span(
                    file_path=relative_path,
                    line_start=1,
                    line_end=line_count,
                    module_id=module.id,
                    file_id=file_id,
                    symbol_id=None,
                    node_type="file",
                )
            )

            adapter = self.parser_factory.get_adapter(relative_path)
            if not adapter:
                continue

            parse_result = adapter.parse_file(str(absolute_path))
            symbol_id_map: dict[str, str] = {}
            local_symbol_candidates: dict[str, list[str]] = {}
            for raw_symbol in parse_result.symbols:
                symbol_id = self._build_symbol_id(module_name, relative_path, raw_symbol.qualified_name)
                for candidate in self._symbol_lookup_candidates(raw_symbol):
                    self._add_lookup_candidate(local_symbol_candidates, candidate, symbol_id)
                symbols.append(
                    raw_symbol.model_copy(
                        update={
                            "id": symbol_id,
                            "file_id": file_id,
                            "module_id": module.id,
                        }
                    )
                )
            symbol_id_map = self._unique_lookup(local_symbol_candidates)
            self._collect_export_lookup_specs(
                specs=export_lookup_specs,
                relative_path=relative_path,
                parse_relations=parse_result.relations,
                import_aliases=parse_result.import_aliases,
                local_symbol_map=symbol_id_map,
            )

            for raw_relation in parse_result.relations:
                pending_relations.append(
                    (
                        raw_relation,
                        module.id,
                        file_id,
                        relative_path,
                        dict(symbol_id_map),
                        dict(parse_result.import_aliases),
                    )
                )

            for raw_span in parse_result.spans:
                spans.append(
                    raw_span.model_copy(
                        update={
                            "file_path": relative_path,
                            "module_id": module.id,
                            "file_id": file_id,
                            "symbol_id": symbol_id_map.get(raw_span.symbol_id or ""),
                        }
                    )
                )

            logger.info(
                "parsed_file",
                extra={
                    "context": {
                        "file_path": relative_path,
                        "symbols": len(parse_result.symbols),
                        "relations": len(parse_result.relations),
                        "file_index": index,
                    }
                },
            )

        repo_meta = RepoMeta(
            repo_id=self._build_repo_id(str(root)),
            repo_path=str(root),
            branch=branch,
            commit_hash=self._get_commit_hash(root),
            scan_time=datetime.now(timezone.utc),
        )
        relations = self._resolve_relations(
            pending_relations,
            modules=list(module_map.values()),
            files=files,
            symbols=symbols,
            export_lookup_specs=export_lookup_specs,
        )
        relations.extend(self._filter_valid_relations(reused_relations, modules=list(module_map.values()), files=files, symbols=symbols))
        relations = self._resequence_relations(relations)
        graph = GraphCode(
            repo_meta=repo_meta,
            modules=sorted(module_map.values(), key=lambda item: item.name),
            files=files,
            symbols=symbols,
            relations=relations,
            spans=spans,
        )
        logger.info(
            "graph_build_completed",
            extra={
                "context": {
                    "repo_path": str(root),
                    "modules": len(graph.modules),
                    "files": len(graph.files),
                    "symbols": len(graph.symbols),
                    "relations": len(graph.relations),
                }
            },
        )
        enriched_graph = self.summary_service.enrich_graph(graph)

        if self.embedding_builder is not None and self.vector_store is not None:
            embedding_start = perf_counter()
            logger.info(
                "embedding_indexing_started",
                extra={
                    "context": {
                        "repo_id": enriched_graph.repo_meta.repo_id,
                        "objects": (
                            len(enriched_graph.modules)
                            + len(enriched_graph.files)
                            + len(enriched_graph.symbols)
                            + len(enriched_graph.relations)
                        ),
                    }
                },
            )
            stale_embedding_ids = self._stale_object_ids(previous_graph, enriched_graph)
            if stale_embedding_ids:
                self.vector_store.delete_embeddings(enriched_graph.repo_meta.repo_id, stale_embedding_ids)
            embeddings = self.embedding_builder.build_embeddings(enriched_graph)
            self.vector_store.save_embeddings(embeddings)
            logger.info(
                "embedding_indexing_completed",
                extra={
                    "context": {
                        "repo_id": enriched_graph.repo_meta.repo_id,
                        "embeddings": len(embeddings),
                        "duration_ms": round((perf_counter() - embedding_start) * 1000, 3),
                    }
                },
            )

        return enriched_graph

    @staticmethod
    def _stale_object_ids(previous_graph: GraphCode | None, current_graph: GraphCode) -> list[str]:
        """Return object ids that existed in the old graph but not the current graph."""

        if previous_graph is None:
            return []
        previous_ids = GraphBuilder._graph_object_ids(previous_graph)
        current_ids = GraphBuilder._graph_object_ids(current_graph)
        return sorted(previous_ids - current_ids)

    @staticmethod
    def _graph_object_ids(graph: GraphCode) -> set[str]:
        return {
            *[module.id for module in graph.modules],
            *[file_obj.id for file_obj in graph.files],
            *[symbol.id for symbol in graph.symbols],
            *[relation.id for relation in graph.relations],
        }

    @staticmethod
    def _infer_module(relative_path: str, repo_name: str) -> tuple[str, str]:
        parts = Path(relative_path).parts
        if len(parts) > 1:
            return parts[0], parts[0]
        return repo_name, "."

    @staticmethod
    def _count_lines(path: Path) -> int:
        with path.open("r", encoding="utf-8") as handle:
            return max(1, sum(1 for _ in handle))

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha1()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _build_repo_id(repo_path: str) -> str:
        digest = hashlib.sha1(repo_path.encode("utf-8")).hexdigest()[:8]
        return f"repo_{digest}"

    @staticmethod
    def _build_file_id(relative_path: str) -> str:
        stem = Path(relative_path).stem
        digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:8]
        return f"F_{stem}_{digest}"

    @staticmethod
    def _build_symbol_id(module_name: str, relative_path: str, qualified_name: str) -> str:
        digest = hashlib.sha1(f"{relative_path}:{qualified_name}".encode("utf-8")).hexdigest()[:8]
        safe_name = qualified_name.replace("/", ".")
        return f"S_{module_name}.{safe_name}_{digest}"

    @classmethod
    def _resolve_relations(
        cls,
        pending_relations: list[tuple[Relation, str, str, str, dict[str, str], dict[str, str]]],
        *,
        modules: list[Module],
        files: list[File],
        symbols: list[Symbol],
        export_lookup_specs: list[tuple[str, str, dict[str, str], dict[str, str]]] | None = None,
    ) -> list[Relation]:
        lookup = cls._build_object_lookup(modules=modules, files=files, symbols=symbols)
        symbols_by_id = {symbol.id: symbol for symbol in symbols}
        files_by_id = {file_obj.id: file_obj for file_obj in files}
        modules_by_id = {module.id: module for module in modules}
        if export_lookup_specs:
            lookup.update(
                cls._build_export_lookup(
                    specs=export_lookup_specs,
                    lookup=lookup,
                    symbols_by_id=symbols_by_id,
                )
            )
        resolved: list[Relation] = []

        for raw_relation, default_module_id, file_id, relative_path, local_symbol_map, import_aliases in pending_relations:
            local_lookup = dict(lookup)
            local_lookup.update(local_symbol_map)
            local_lookup[relative_path] = file_id

            source_id = cls._resolve_relation_endpoint(raw_relation.source_id, local_lookup, import_aliases)
            target_id = cls._resolve_relation_endpoint(raw_relation.target_id, local_lookup, import_aliases)
            source_module_id = cls._resolve_endpoint_module_id(
                source_id,
                default_module_id=default_module_id,
                symbols_by_id=symbols_by_id,
                files_by_id=files_by_id,
                modules_by_id=modules_by_id,
            )
            target_module_id = cls._resolve_endpoint_module_id(
                target_id,
                default_module_id=default_module_id,
                symbols_by_id=symbols_by_id,
                files_by_id=files_by_id,
                modules_by_id=modules_by_id,
            )
            resolved.append(
                raw_relation.model_copy(
                    update={
                        "id": f"R_{len(resolved) + 1}",
                        "source_id": source_id,
                        "target_id": target_id,
                        "source_module_id": source_module_id,
                        "target_module_id": target_module_id,
                    }
                )
            )
        return resolved

    @staticmethod
    def _build_object_lookup(
        *,
        modules: list[Module],
        files: list[File],
        symbols: list[Symbol],
    ) -> dict[str, str]:
        candidates: dict[str, list[str]] = {}
        files_by_id = {file_obj.id: file_obj for file_obj in files}
        for module in modules:
            GraphBuilder._add_lookup_candidate(candidates, module.id, module.id)
            GraphBuilder._add_lookup_candidate(candidates, module.name, module.id)
            GraphBuilder._add_lookup_candidate(candidates, module.path, module.id)
        for file_obj in files:
            GraphBuilder._add_lookup_candidate(candidates, file_obj.id, file_obj.id)
            GraphBuilder._add_lookup_candidate(candidates, file_obj.path, file_obj.id)
            GraphBuilder._add_lookup_candidate(candidates, file_obj.name, file_obj.id)
        for symbol in symbols:
            for candidate in GraphBuilder._symbol_lookup_candidates(symbol):
                GraphBuilder._add_lookup_candidate(candidates, candidate, symbol.id)
            file_obj = files_by_id.get(symbol.file_id)
            if file_obj is not None:
                stem = Path(file_obj.path).stem
                GraphBuilder._add_lookup_candidate(candidates, f"{stem}.{symbol.name}", symbol.id)
                GraphBuilder._add_lookup_candidate(candidates, f"{stem}.{symbol.qualified_name}", symbol.id)
                for candidate in GraphBuilder._path_scoped_symbol_candidates(file_obj.path, symbol):
                    GraphBuilder._add_lookup_candidate(candidates, candidate, symbol.id)
        return GraphBuilder._unique_lookup(candidates)

    @staticmethod
    def _add_lookup_candidate(candidates: dict[str, list[str]], key: str, object_id: str) -> None:
        if key:
            candidates.setdefault(key, []).append(object_id)

    @staticmethod
    def _symbol_lookup_candidates(symbol: Symbol) -> list[str]:
        candidates = [symbol.id, symbol.qualified_name, symbol.name]
        for separator in (".", "::"):
            parts = [part for part in symbol.qualified_name.split(separator) if part]
            if len(parts) > 1:
                candidates.append(parts[-1])
                candidates.append(separator.join(parts[-2:]))
        return list(dict.fromkeys(candidate for candidate in candidates if candidate))

    @staticmethod
    def _path_scoped_symbol_candidates(relative_path: str, symbol: Symbol) -> list[str]:
        path = Path(relative_path)
        suffixless_parts = list(path.with_suffix("").parts)
        if not suffixless_parts:
            return []

        normalized_parts = suffixless_parts[:]
        if normalized_parts[-1] == "mod" and len(normalized_parts) > 1:
            normalized_parts = normalized_parts[:-1]

        scope_dot = ".".join(normalized_parts)
        scope_rust = "::".join(normalized_parts[1:] if normalized_parts[:1] == ["src"] else normalized_parts)
        candidates = []

        if scope_dot:
            candidates.append(f"{scope_dot}.{symbol.name}")
            candidates.append(f"{scope_dot}.{symbol.qualified_name}")
        if scope_rust:
            candidates.append(f"{scope_rust}::{symbol.name}")
            candidates.append(f"{scope_rust}::{symbol.qualified_name}")
            if "." in symbol.qualified_name:
                candidates.append(f"{scope_rust}::{symbol.qualified_name.replace('.', '::')}")
        return list(dict.fromkeys(candidate for candidate in candidates if candidate))

    @staticmethod
    def _unique_lookup(candidates: dict[str, list[str]]) -> dict[str, str]:
        return {
            key: object_ids[0]
            for key, object_ids in candidates.items()
            if len(set(object_ids)) == 1
        }

    @staticmethod
    def _resolve_relation_endpoint(raw_id: str, lookup: dict[str, str], import_aliases: dict[str, str]) -> str:
        normalized = raw_id.strip()
        if normalized in lookup:
            return lookup[normalized]
        alternate_forms = GraphBuilder._alternate_lookup_forms(normalized)
        for candidate in alternate_forms:
            if candidate in lookup:
                return lookup[candidate]
        imported = GraphBuilder._resolve_import_alias(normalized, import_aliases)
        if imported and imported in lookup:
            return lookup[imported]
        if imported and f"{imported}.default" in lookup:
            return lookup[f"{imported}.default"]
        if imported:
            for candidate in GraphBuilder._alternate_lookup_forms(imported):
                if candidate in lookup:
                    return lookup[candidate]
                default_candidate = f"{candidate}.default"
                if default_candidate in lookup:
                    return lookup[default_candidate]
        for separator in (".", "::", "->"):
            if separator in normalized:
                short_name = normalized.split(separator)[-1]
                if short_name in lookup:
                    return lookup[short_name]
        if imported:
            for separator in (".", "::", "->"):
                if separator in imported:
                    short_name = imported.split(separator)[-1]
                    if short_name in lookup:
                        return lookup[short_name]
        return normalized

    @staticmethod
    def _alternate_lookup_forms(identifier: str) -> list[str]:
        candidates = [identifier]
        if "::" in identifier:
            candidates.append(identifier.replace("::", "."))
        if "." in identifier:
            candidates.append(identifier.replace(".", "::"))
        if "->" in identifier:
            candidates.append(identifier.replace("->", "::"))
            candidates.append(identifier.replace("->", "."))
        return list(dict.fromkeys(candidate for candidate in candidates if candidate))

    @staticmethod
    def _resolve_import_alias(raw_id: str, import_aliases: dict[str, str]) -> str | None:
        if raw_id in import_aliases:
            return import_aliases[raw_id]

        for separator in (".", "::", "->"):
            if separator not in raw_id:
                continue
            head, tail = raw_id.split(separator, 1)
            if head in import_aliases:
                mapped = import_aliases[head]
                if separator in {"::", "->"}:
                    return f"{mapped}::{tail.replace('->', '::')}"
                return f"{mapped}.{tail}"
        return None

    @staticmethod
    def _resolve_endpoint_module_id(
        object_id: str,
        *,
        default_module_id: str,
        symbols_by_id: dict[str, Symbol],
        files_by_id: dict[str, File],
        modules_by_id: dict[str, Module],
    ) -> str:
        if object_id in symbols_by_id:
            return symbols_by_id[object_id].module_id
        if object_id in files_by_id:
            return files_by_id[object_id].module_id
        if object_id in modules_by_id:
            return object_id
        return default_module_id

    @staticmethod
    def _group_symbols_by_file(symbols: list[Symbol]) -> dict[str, list[Symbol]]:
        grouped: dict[str, list[Symbol]] = {}
        for symbol in symbols:
            grouped.setdefault(symbol.file_id, []).append(symbol)
        return grouped

    @staticmethod
    def _group_spans_by_file(spans: list[Span]) -> dict[str, list[Span]]:
        grouped: dict[str, list[Span]] = {}
        for span in spans:
            if span.file_id and span.node_type != "file":
                grouped.setdefault(span.file_id, []).append(span)
        return grouped

    @staticmethod
    def _group_relations_by_file(relations: list[Relation], symbols: list[Symbol]) -> dict[str, list[Relation]]:
        symbol_to_file = {symbol.id: symbol.file_id for symbol in symbols}
        grouped: dict[str, list[Relation]] = {}
        for relation in relations:
            file_id = symbol_to_file.get(relation.source_id)
            if file_id:
                grouped.setdefault(file_id, []).append(relation)
        return grouped

    @staticmethod
    def _filter_valid_relations(
        relations: list[Relation],
        *,
        modules: list[Module],
        files: list[File],
        symbols: list[Symbol],
    ) -> list[Relation]:
        module_ids = {module.id for module in modules}
        file_ids = {file_obj.id for file_obj in files}
        symbol_ids = {symbol.id for symbol in symbols}
        valid: list[Relation] = []
        for relation in relations:
            if relation.source_type == "symbol" and relation.source_id not in symbol_ids:
                continue
            if relation.source_type == "file" and relation.source_id not in file_ids:
                continue
            if relation.source_type == "module" and relation.source_id not in module_ids:
                continue
            if relation.target_type == "symbol" and relation.target_id not in symbol_ids:
                continue
            if relation.target_type == "file" and relation.target_id not in file_ids:
                continue
            if relation.target_type == "module" and relation.target_id not in module_ids:
                continue
            valid.append(relation)
        return valid

    @staticmethod
    def _resequence_relations(relations: list[Relation]) -> list[Relation]:
        return [
            relation.model_copy(update={"id": f"R_{index}"})
            for index, relation in enumerate(relations, start=1)
        ]

    @staticmethod
    def _collect_export_lookup_specs(
        *,
        specs: list[tuple[str, str, dict[str, str], dict[str, str]]],
        relative_path: str,
        parse_relations: list[Relation],
        import_aliases: dict[str, str],
        local_symbol_map: dict[str, str],
    ) -> None:
        stem = Path(relative_path).stem
        for relation in parse_relations:
            if relation.relation_type != "exports":
                continue
            export_name = relation.target_id.removeprefix("export:")
            specs.append((f"{stem}.{export_name}", relation.source_id, dict(import_aliases), dict(local_symbol_map)))

    @classmethod
    def _build_export_lookup(
        cls,
        *,
        specs: list[tuple[str, str, dict[str, str], dict[str, str]]],
        lookup: dict[str, str],
        symbols_by_id: dict[str, Symbol],
    ) -> dict[str, str]:
        candidates: dict[str, list[str]] = {}
        for export_key, raw_source_id, import_aliases, local_symbol_map in specs:
            local_lookup = dict(lookup)
            local_lookup.update(local_symbol_map)
            resolved_source_id = cls._resolve_relation_endpoint(raw_source_id, local_lookup, import_aliases)
            if resolved_source_id in symbols_by_id:
                cls._add_lookup_candidate(candidates, export_key, resolved_source_id)
        return cls._unique_lookup(candidates)

    @staticmethod
    def _get_commit_hash(root: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return "unknown"
        return result.stdout.strip()
