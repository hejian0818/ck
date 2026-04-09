"""Document skeleton planning and generation."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.models.doc_models import DocumentResult, DocumentSkeleton, SectionContent, SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.retrieval.doc_retriever import DocRetriever, SectionRetrievalResult
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore

GraphObject = Module | File | Symbol
_API_SYMBOL_TYPES = {"route", "controller", "endpoint", "api"}


class SkeletonPlanner:
    """Plan a document skeleton from repository graph structure."""

    def __init__(self, repository: GraphRepository) -> None:
        self.repository = repository

    def plan(self, repo_id: str) -> DocumentSkeleton:
        """Build a document skeleton from repository metadata and graph structure."""

        modules = self.repository.list_modules(repo_id)
        relations = self.repository.list_relations(repo_id)
        title = f"{self._resolve_repo_name(repo_id)} Design Document"
        sections: list[SectionPlan] = [
            SectionPlan(
                section_id="overview",
                title="概述",
                level=1,
                section_type="overview",
                target_object_ids=[module.id for module in modules],
                description="总结仓库的主要模块、职责边界和整体用途。",
            ),
            SectionPlan(
                section_id="architecture",
                title="架构总览",
                level=1,
                section_type="architecture",
                target_object_ids=[module.id for module in modules],
                description="说明系统分层、核心模块协作关系和主要架构约束。",
            ),
        ]

        for module in modules:
            sections.append(self._build_module_section(module))
            sections.extend(self._build_file_sections(module))

        if self._has_cross_module_dependencies(relations):
            sections.append(
                SectionPlan(
                    section_id="dependency-analysis",
                    title="依赖分析",
                    level=1,
                    section_type="dependency",
                    target_object_ids=sorted(
                        {
                            relation.source_module_id
                            for relation in relations
                            if relation.source_module_id != relation.target_module_id
                        }
                        | {
                            relation.target_module_id
                            for relation in relations
                            if relation.source_module_id != relation.target_module_id
                        }
                    ),
                    description="分析跨模块依赖、调用方向和潜在耦合点。",
                )
            )

        api_symbols = self._collect_api_symbols(modules)
        if api_symbols:
            sections.append(
                SectionPlan(
                    section_id="api",
                    title="API 设计",
                    level=1,
                    section_type="api",
                    target_object_ids=[symbol.id for symbol in api_symbols],
                    description="整理对外暴露的路由、控制器和接口调用链。",
                )
            )

        sections.append(
            SectionPlan(
                section_id="summary",
                title="总结",
                level=1,
                section_type="summary",
                target_object_ids=[module.id for module in modules],
                description="总结系统职责分工、关键依赖和后续维护关注点。",
            )
        )
        return DocumentSkeleton(repo_id=repo_id, title=title, sections=sections)

    def _build_module_section(self, module: Module) -> SectionPlan:
        return SectionPlan(
            section_id=f"module-{module.id}",
            title=module.name,
            level=2,
            section_type="module",
            target_object_ids=[module.id],
            description=f"说明模块 {module.name} 的职责、内部文件构成和关键符号。",
        )

    def _build_file_sections(self, module: Module) -> list[SectionPlan]:
        files = self.repository.list_files_by_module(module.id)
        ranked_files = sorted(
            files,
            key=lambda file_obj: (-self._file_priority(file_obj), file_obj.path),
        )
        sections: list[SectionPlan] = []
        for file_obj in ranked_files[: settings.DOC_PLANNER_MAX_FILES_PER_MODULE]:
            sections.append(
                SectionPlan(
                    section_id=f"file-{file_obj.id}",
                    title=file_obj.name,
                    level=3,
                    section_type="module",
                    target_object_ids=[file_obj.id],
                    description=f"说明文件 {file_obj.path} 在模块 {module.name} 中承担的实现职责。",
                )
            )
        return sections

    def _file_priority(self, file_obj: File) -> int:
        symbols = self.repository.list_symbols_by_file(file_obj.id)
        summary_bonus = 1 if file_obj.summary else 0
        return len(symbols) + summary_bonus

    def _collect_api_symbols(self, modules: list[Module]) -> list[Symbol]:
        symbols: list[Symbol] = []
        for module in modules:
            for symbol in self.repository.list_symbols_by_module(module.id):
                normalized_type = symbol.type.lower()
                normalized_name = symbol.qualified_name.lower()
                if normalized_type in _API_SYMBOL_TYPES or any(
                    hint in normalized_name for hint in ("route", "controller", "endpoint", "api")
                ):
                    symbols.append(symbol)
        return symbols

    @staticmethod
    def _has_cross_module_dependencies(relations: list[Relation]) -> bool:
        return any(relation.source_module_id != relation.target_module_id for relation in relations)

    def _resolve_repo_name(self, repo_id: str) -> str:
        repo_path = self.repository.get_repo_path(repo_id)
        if not repo_path:
            return repo_id
        return Path(repo_path).name or repo_id


class DocAgent:
    """Coordinate planning, retrieval, and deterministic section rendering."""

    def __init__(
        self,
        repository: GraphRepository,
        planner: SkeletonPlanner | None = None,
        retriever: DocRetriever | None = None,
    ) -> None:
        self.repository = repository
        self.planner = planner or SkeletonPlanner(repository)
        self.retriever = retriever or DocRetriever(
            repository,
            embedding_builder=EmbeddingBuilder(),
            vector_store=VectorStore(settings.DATABASE_URL),
        )

    def plan(self, repo_id: str) -> DocumentSkeleton:
        """Return an auto-generated document skeleton."""

        return self.planner.plan(repo_id)

    def generate(self, repo_id: str, skeleton: DocumentSkeleton | None = None) -> DocumentResult:
        """Generate deterministic markdown content for all planned sections."""

        active_skeleton = skeleton or self.plan(repo_id)
        sections = [
            self._generate_section(repo_id=repo_id, section=section)
            for section in active_skeleton.sections
        ]
        return DocumentResult(
            repo_id=repo_id,
            title=active_skeleton.title,
            sections=sections,
            metadata={
                "section_count": len(sections),
                "generated_from_custom_skeleton": skeleton is not None,
            },
        )

    def list_sections(self, repo_id: str) -> list[SectionPlan]:
        """Return planned sections for a repository."""

        return self.plan(repo_id).sections

    def _generate_section(self, repo_id: str, section: SectionPlan) -> SectionContent:
        retrieval = self.retriever.retrieve(repo_id=repo_id, section=section)
        content = self._render_section_content(retrieval)
        used_objects = [object_.id for object_ in retrieval.objects]
        confidence = self._section_confidence(retrieval)
        return SectionContent(
            section_id=section.section_id,
            title=section.title,
            content=content,
            diagrams=[],
            used_objects=used_objects,
            confidence=confidence,
        )

    def _render_section_content(self, retrieval: SectionRetrievalResult) -> str:
        section = retrieval.section
        lines = [section.description]
        summaries = [self._describe_object(object_) for object_ in retrieval.objects[: settings.DOC_RETRIEVAL_TOP_K]]
        if summaries:
            lines.append("")
            lines.append("关键对象:")
            lines.extend(f"- {summary}" for summary in summaries)

        relation_lines = [self._describe_relation(relation) for relation in retrieval.relations[: settings.DOC_VECTOR_TOP_K]]
        if relation_lines:
            lines.append("")
            lines.append("关键关系:")
            lines.extend(f"- {line}" for line in relation_lines)

        return "\n".join(lines)

    def _describe_object(self, object_: GraphObject) -> str:
        if isinstance(object_, Module):
            summary = self._extract_summary_text(object_.summary, object_.name)
            return f"模块 `{object_.name}`: {summary}"
        if isinstance(object_, File):
            summary = self._extract_summary_text(object_.summary, object_.path)
            return f"文件 `{object_.path}`: {summary}"
        summary = self._extract_summary_text(object_.summary or object_.doc, object_.qualified_name)
        return f"符号 `{object_.qualified_name}` ({object_.type}): {summary}"

    def _describe_relation(self, relation: Relation) -> str:
        summary = self._extract_summary_text(relation.summary, relation.relation_type)
        return (
            f"`{relation.source_id}` {relation.relation_type} `{relation.target_id}`"
            f": {summary}"
        )

    @staticmethod
    def _extract_summary_text(raw_summary: str, fallback: str) -> str:
        if not raw_summary:
            return fallback
        try:
            payload = json.loads(raw_summary)
        except json.JSONDecodeError:
            return raw_summary

        if isinstance(payload, dict):
            for key in ("summary", "purpose", "description", "module_path", "file_path", "symbol_name"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
        return fallback

    @staticmethod
    def _section_confidence(retrieval: SectionRetrievalResult) -> float:
        if not retrieval.object_scores:
            return 0.2 if retrieval.objects else 0.0
        top_scores = sorted(retrieval.object_scores.values(), reverse=True)[:3]
        return round(sum(top_scores) / len(top_scores), 4)
