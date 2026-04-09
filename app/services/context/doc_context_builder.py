"""Build LLM-ready context for document section generation."""

from __future__ import annotations

import json

from app.core.config import settings
from app.models.doc_models import SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.retrieval.doc_retriever import SectionRetrievalResult

GraphObject = Module | File | Symbol
_MAX_CONTEXT_OBJECTS = 8
_MAX_CONTEXT_RELATIONS = 6

_SECTION_GUIDANCE = {
    "overview": [
        "概括仓库目标、主要模块和整体协作方式。",
        "说明核心模块边界，不要逐行解释实现细节。",
        "如果存在明显的模块分层或入口路径，明确写出。",
    ],
    "architecture": [
        "描述系统结构、关键分层和跨模块协作。",
        "优先解释核心约束、依赖方向和职责划分。",
    ],
    "module": [
        "说明模块或文件的核心职责。",
        "列出重要文件、关键符号签名和职责分工。",
        "如果能看出主要实现流程，做简要说明。",
    ],
    "api": [
        "描述对外接口、请求处理入口和核心调用链。",
        "优先说明路由、控制器、服务调用和输入输出模型。",
    ],
    "data_flow": [
        "按顺序描述关键数据流转路径。",
        "重点解释数据从入口到下游处理的传递过程。",
    ],
    "dependency": [
        "总结模块间依赖方向、依赖类型和耦合点。",
        "指出关键外部依赖或跨模块调用关系。",
    ],
    "summary": [
        "总结系统职责、关键依赖和维护关注点。",
        "避免重复展开细节，以结论性表述为主。",
    ],
}


class DocContextBuilder:
    """Assemble structured prompts for section-level document generation."""

    def build_context(self, section: SectionPlan, retrieval: SectionRetrievalResult) -> str:
        """Return a section-specific prompt for markdown paragraph generation."""

        ranked_objects = self._rank_objects(retrieval)
        ranked_relations = self._rank_relations(retrieval, ranked_objects)
        guidance = _SECTION_GUIDANCE.get(section.section_type, _SECTION_GUIDANCE["summary"])

        lines = [
            "你是资深架构文档工程师，请基于给定代码图谱上下文撰写设计文档段落。",
            "输出要求:",
            f"- 使用 Markdown 编写，标题级别与当前段落 level={section.level} 对齐。",
            f"- 段落标题使用 `{self._heading_prefix(section.level)} {section.title}`。",
            "- 使用简洁、可验证的陈述，避免编造缺失信息。",
            "- 不要输出与当前 section 无关的内容。",
            "",
            "段落信息:",
            f"- section_id: {section.section_id}",
            f"- section_type: {section.section_type}",
            f"- title: {section.title}",
            f"- description: {section.description}",
            "",
            "写作重点:",
        ]
        lines.extend(f"- {item}" for item in guidance)
        lines.extend(
            [
                "",
                "可用对象:",
                *self._format_objects(ranked_objects),
                "",
                "可用关系:",
                *self._format_relations(ranked_relations),
                "",
                "请生成最终 Markdown 段落。",
            ]
        )
        return "\n".join(lines)

    def _rank_objects(self, retrieval: SectionRetrievalResult) -> list[GraphObject]:
        ordered = sorted(
            retrieval.objects,
            key=lambda object_: (
                -retrieval.object_scores.get(object_.id, 0.0),
                self._object_priority(object_),
                object_.id,
            ),
        )
        return ordered[: min(settings.DOC_RETRIEVAL_TOP_K, _MAX_CONTEXT_OBJECTS)]

    def _rank_relations(
        self,
        retrieval: SectionRetrievalResult,
        objects: list[GraphObject],
    ) -> list[Relation]:
        object_ids = {object_.id for object_ in objects}
        prioritized = [
            relation
            for relation in retrieval.relations
            if relation.source_id in object_ids or relation.target_id in object_ids
        ]
        if not prioritized:
            prioritized = list(retrieval.relations)
        return prioritized[: min(settings.DOC_VECTOR_TOP_K + 1, _MAX_CONTEXT_RELATIONS)]

    @staticmethod
    def _object_priority(object_: GraphObject) -> int:
        if isinstance(object_, Module):
            return 0
        if isinstance(object_, File):
            return 1
        return 2

    def _format_objects(self, objects: list[GraphObject]) -> list[str]:
        if not objects:
            return ["- <none>"]
        return [f"- {self._describe_object(object_)}" for object_ in objects]

    def _format_relations(self, relations: list[Relation]) -> list[str]:
        if not relations:
            return ["- <none>"]
        return [f"- {self._describe_relation(relation)}" for relation in relations]

    def _describe_object(self, object_: GraphObject) -> str:
        if isinstance(object_, Module):
            return (
                f"模块 `{object_.name}` (id={object_.id}, path={object_.path})"
                f": {self._extract_summary_text(object_.summary, object_.path)}"
            )
        if isinstance(object_, File):
            return (
                f"文件 `{object_.path}` (language={object_.language})"
                f": {self._extract_summary_text(object_.summary, object_.name)}"
            )

        detail_parts = [f"type={object_.type}", f"signature={object_.signature or '<none>'}"]
        return (
            f"符号 `{object_.qualified_name}` ({', '.join(detail_parts)})"
            f": {self._extract_summary_text(object_.summary or object_.doc, object_.name)}"
        )

    def _describe_relation(self, relation: Relation) -> str:
        return (
            f"`{relation.source_id}` -[{relation.relation_type}]-> `{relation.target_id}`"
            f": {self._extract_summary_text(relation.summary, relation.relation_type)}"
        )

    @staticmethod
    def _heading_prefix(level: int) -> str:
        return "#" * max(level, 1)

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
