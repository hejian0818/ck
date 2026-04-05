"""Repository graph builder."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.core.logging import get_logger
from app.models.graph_objects import File, GraphCode, Module, Relation, RepoMeta, Span, Symbol
from app.services.cleanarch.parser_factory import ParserFactory
from app.services.cleanarch.scanner import RepoScanner
from app.services.indexing.summary_builder import SummaryGenerationService

logger = get_logger(__name__)


class GraphBuilder:
    """Build GraphCode from a repository."""

    def __init__(
        self,
        scanner: RepoScanner | None = None,
        parser_factory: ParserFactory | None = None,
        summary_service: SummaryGenerationService | None = None,
    ) -> None:
        self.scanner = scanner or RepoScanner()
        self.parser_factory = parser_factory or ParserFactory()
        self.summary_service = summary_service or SummaryGenerationService()

    def build_graph(self, repo_path: str, branch: str = "main") -> GraphCode:
        """Build a graph representation from a repository."""

        root = Path(repo_path).resolve()
        file_paths = self.scanner.scan_repository(str(root))
        module_map: dict[str, Module] = {}
        files: list[File] = []
        symbols: list[Symbol] = []
        relations: list[Relation] = []
        spans: list[Span] = []

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
            language = self.parser_factory.detect_language(relative_path)
            line_count = self._count_lines(absolute_path)
            file_id = self._build_file_id(relative_path)
            file_obj = File(
                id=file_id,
                name=absolute_path.name,
                path=relative_path,
                module_id=module.id,
                language=language,
                start_line=1,
                end_line=line_count,
            )
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
            for raw_symbol in parse_result.symbols:
                symbol_id = self._build_symbol_id(module_name, relative_path, raw_symbol.qualified_name)
                symbol_id_map[raw_symbol.qualified_name] = symbol_id
                symbols.append(
                    raw_symbol.model_copy(
                        update={
                            "id": symbol_id,
                            "file_id": file_id,
                            "module_id": module.id,
                        }
                    )
                )

            for raw_relation in parse_result.relations:
                source_id = symbol_id_map.get(raw_relation.source_id, raw_relation.source_id)
                target_id = symbol_id_map.get(raw_relation.target_id, raw_relation.target_id)
                relations.append(
                    raw_relation.model_copy(
                        update={
                            "id": f"R_{len(relations) + 1}",
                            "source_id": source_id,
                            "target_id": target_id,
                            "source_module_id": module.id,
                            "target_module_id": module.id,
                        }
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
        return self.summary_service.enrich_graph(graph)

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
