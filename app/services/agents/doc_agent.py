"""Document skeleton planning and generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.models.doc_models import DocumentResult, DocumentSkeleton, SectionContent, SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.context.doc_context_builder import DocContextBuilder
from app.services.diagrams.plantuml_generator import PlantUMLGenerator
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.retrieval.doc_retriever import DocRetriever, SectionRetrievalResult
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore

GraphObject = Module | File | Symbol
_API_SYMBOL_TYPES = {"route", "controller", "endpoint", "api"}
_CLASS_SYMBOL_TYPES = {"class", "interface"}
_SEQUENCE_SECTION_TYPES = {"api", "data_flow"}


class DocLLMClient(Protocol):
    """Protocol for pluggable paragraph generators."""

    def generate(self, section: SectionPlan, retrieval: SectionRetrievalResult, prompt: str) -> str:
        """Generate markdown content for a document section."""


class DeterministicDocLLMClient:
    """Deterministic fallback paragraph generator for offline document rendering."""

    def generate(self, section: SectionPlan, retrieval: SectionRetrievalResult, prompt: str) -> str:  # noqa: ARG002
        subheading = "#" * (max(section.level, 1) + 1)
        lines = [f"{'#' * max(section.level, 1)} {section.title}", "", section.description]

        objects = retrieval.objects[: settings.DOC_RETRIEVAL_TOP_K]
        if objects:
            lines.extend(["", f"{subheading} 关键对象", "关键对象:"])
            for object_ in objects:
                lines.append(f"- {DocAgent.describe_object(object_)}")

        relations = retrieval.relations[: settings.DOC_VECTOR_TOP_K]
        if relations:
            lines.extend(["", f"{subheading} 关键关系", "关键关系:"])
            for relation in relations:
                lines.append(f"- {DocAgent.describe_relation(relation)}")

        conclusion = self._build_conclusion(section, retrieval)
        if conclusion:
            lines.extend(["", f"{subheading} 说明", conclusion])

        return "\n".join(lines).strip()

    def _build_conclusion(self, section: SectionPlan, retrieval: SectionRetrievalResult) -> str:
        if section.section_type == "overview":
            module_names = [object_.name for object_ in retrieval.objects if isinstance(object_, Module)]
            if module_names:
                return f"系统当前主要由 {', '.join(module_names[:4])} 等模块组成，并通过明确的职责边界协作。"
        if section.section_type == "dependency":
            dependencies = [relation.relation_type for relation in retrieval.relations]
            if dependencies:
                return f"跨模块关系以 {', '.join(sorted(set(dependencies)))} 为主，需要重点关注依赖方向的一致性。"
        if section.section_type in _SEQUENCE_SECTION_TYPES:
            return "调用链展示了入口逻辑与下游实现之间的衔接顺序，可据此继续补充接口和数据约束。"
        if section.section_type == "summary":
            return "后续维护应优先关注核心模块边界、关键调用链和跨模块依赖变化。"
        return "以上信息基于当前检索到的代码图谱对象整理。"


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
    """Coordinate planning, retrieval, paragraph generation, and diagram rendering."""

    def __init__(
        self,
        repository: GraphRepository,
        planner: SkeletonPlanner | None = None,
        retriever: DocRetriever | None = None,
        context_builder: DocContextBuilder | None = None,
        diagram_generator: PlantUMLGenerator | None = None,
        llm_client: DocLLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.planner = planner or SkeletonPlanner(repository)
        self.retriever = retriever or DocRetriever(
            repository,
            embedding_builder=EmbeddingBuilder(),
            vector_store=VectorStore(settings.DATABASE_URL),
        )
        self.context_builder = context_builder or DocContextBuilder()
        self.diagram_generator = diagram_generator or PlantUMLGenerator()
        self.llm_client = llm_client or DeterministicDocLLMClient()

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
        try:
            retrieval = self.retriever.retrieve(repo_id=repo_id, section=section)
            prompt = self.context_builder.build_context(section, retrieval)
            raw_content = self.llm_client.generate(section, retrieval, prompt)
            content = self._post_process_markdown(section, raw_content)
            diagrams = self._generate_diagrams(repo_id, section, retrieval)
            used_objects = [object_.id for object_ in retrieval.objects]
            confidence = self._section_confidence(retrieval, content)
            return SectionContent(
                section_id=section.section_id,
                title=section.title,
                content=content,
                diagrams=diagrams,
                used_objects=used_objects,
                confidence=confidence,
            )
        except Exception:
            return SectionContent(
                section_id=section.section_id,
                title=section.title,
                content=self._failed_section_markdown(section),
                diagrams=[],
                used_objects=[],
                confidence=0.0,
            )

    @staticmethod
    def describe_object(object_: GraphObject) -> str:
        if isinstance(object_, Module):
            summary = DocAgent._extract_summary_text(object_.summary, object_.name)
            return f"模块 `{object_.name}`: {summary}"
        if isinstance(object_, File):
            summary = DocAgent._extract_summary_text(object_.summary, object_.path)
            return f"文件 `{object_.path}`: {summary}"
        summary = DocAgent._extract_summary_text(object_.summary or object_.doc, object_.qualified_name)
        return f"符号 `{object_.qualified_name}` ({object_.type}): {summary}"

    @staticmethod
    def describe_relation(relation: Relation) -> str:
        summary = DocAgent._extract_summary_text(relation.summary, relation.relation_type)
        return (
            f"`{relation.source_id}` {relation.relation_type} `{relation.target_id}`"
            f": {summary}"
        )

    def _post_process_markdown(self, section: SectionPlan, content: str) -> str:
        normalized = content.strip()
        if not normalized:
            raise ValueError(f"empty content for section {section.section_id}")

        heading = f"{'#' * max(section.level, 1)} {section.title}"
        if not normalized.startswith("#"):
            normalized = f"{heading}\n\n{normalized}"
        elif not normalized.startswith(heading):
            parts = normalized.splitlines()
            parts[0] = heading
            normalized = "\n".join(parts)

        return normalized.replace("\r\n", "\n")

    def _generate_diagrams(
        self,
        repo_id: str,
        section: SectionPlan,
        retrieval: SectionRetrievalResult,
    ) -> list[str]:
        try:
            if section.section_type == "overview":
                modules = [object_ for object_ in retrieval.objects if isinstance(object_, Module)]
                if modules:
                    relations = [
                        relation
                        for relation in self.repository.list_relations(repo_id)
                        if relation.source_module_id != relation.target_module_id
                    ]
                    return [self.diagram_generator.generate_component_diagram(modules, relations)]

            if section.section_type == "module":
                class_symbols = [
                    object_
                    for object_ in retrieval.objects
                    if isinstance(object_, Symbol) and object_.type.lower() in _CLASS_SYMBOL_TYPES
                ]
                if class_symbols:
                    relations = self._collect_symbol_relations(class_symbols)
                    return [self.diagram_generator.generate_class_diagram(class_symbols, relations)]

            if section.section_type in _SEQUENCE_SECTION_TYPES:
                entry_symbol = self._resolve_entry_symbol(retrieval)
                call_chain = [relation for relation in retrieval.relations if relation.relation_type.lower() == "calls"]
                if entry_symbol is not None and call_chain:
                    return [self.diagram_generator.generate_sequence_diagram(entry_symbol, call_chain)]
        except Exception:
            return []
        return []

    def _resolve_entry_symbol(self, retrieval: SectionRetrievalResult) -> Symbol | None:
        symbols = [object_ for object_ in retrieval.objects if isinstance(object_, Symbol)]
        if not symbols:
            return None

        source_ids = {relation.source_id for relation in retrieval.relations if relation.relation_type.lower() == "calls"}
        for symbol in symbols:
            if symbol.id in source_ids:
                return symbol
        return symbols[0]

    def _collect_symbol_relations(self, symbols: list[Symbol]) -> list[Relation]:
        relation_map: dict[str, Relation] = {}
        symbol_ids = {symbol.id for symbol in symbols}
        for symbol in symbols:
            candidates = self.repository.get_relations_by_source(symbol.id)
            candidates.extend(self.repository.get_relations_by_target(symbol.id))
            for relation in candidates:
                if relation.source_id in symbol_ids and relation.target_id in symbol_ids:
                    relation_map[relation.id] = relation
        return list(relation_map.values())

    def _failed_section_markdown(self, section: SectionPlan) -> str:
        return "\n".join(
            [
                f"{'#' * max(section.level, 1)} {section.title}",
                "",
                "本文段生成失败，当前结果已跳过，不影响其他段落输出。",
            ]
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
    def _section_confidence(retrieval: SectionRetrievalResult, content: str) -> float:
        if not content.strip():
            return 0.0
        if not retrieval.object_scores:
            return 0.2 if retrieval.objects else 0.0
        top_scores = sorted(retrieval.object_scores.values(), reverse=True)[:3]
        return round(sum(top_scores) / len(top_scores), 4)
