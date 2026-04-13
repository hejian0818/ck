"""Build LLM-ready QA context."""

from __future__ import annotations

from pathlib import Path

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Relation, Symbol
from app.models.qa_models import CodeSelection, GraphObject, RetrievalResult


class ContextBuilder:
    """Assemble a structured text context for QA."""

    def build_context(
        self,
        question: str,
        selection: CodeSelection | None,
        anchor: Anchor,
        retrieval_result: RetrievalResult,
        memory_summary: str = "",
        max_context_tokens: int = 2000,
    ) -> str:
        code_snippet = self._load_code_snippet(selection)
        current_object = retrieval_result.current_object
        related_objects = list(retrieval_result.related_objects)
        relations = list(retrieval_result.relations)

        context = self._compose_context(
            question=question,
            code_snippet=code_snippet,
            anchor=anchor,
            retrieval_result=retrieval_result,
            current_object=current_object,
            related_objects=related_objects,
            relations=relations,
            memory_summary=memory_summary,
        )
        while self._estimate_tokens(context) > max_context_tokens and (relations or related_objects):
            if relations:
                relations.pop()
            elif related_objects:
                related_objects.pop()
            context = self._compose_context(
                question=question,
                code_snippet=code_snippet,
                anchor=anchor,
                retrieval_result=retrieval_result,
                current_object=current_object,
                related_objects=related_objects,
                relations=relations,
                memory_summary=memory_summary,
            )
        return context

    def _compose_context(
        self,
        question: str,
        code_snippet: str,
        anchor: Anchor,
        retrieval_result: RetrievalResult,
        current_object: GraphObject | None,
        related_objects: list[Module | File | Symbol],
        relations: list[Relation],
        memory_summary: str,
    ) -> str:
        file_info = self._describe_file(current_object, retrieval_result)
        module_info = self._describe_module(current_object, retrieval_result)
        callers = [
            relation.source_id
            for relation in relations
            if anchor.symbol_id and relation.target_id == anchor.symbol_id
        ]
        callees = [
            relation.target_id
            for relation in relations
            if anchor.symbol_id and relation.source_id == anchor.symbol_id
        ]
        anchor_target = anchor.symbol_id or anchor.file_id or anchor.module_id or "none"
        related_object_lines = [self._describe_object(object_) for object_ in related_objects]
        relation_lines = [self._describe_relation(relation) for relation in relations]

        return "\n".join(
            [
                f"当前问题: {question}",
                "",
                "会话状态摘要:",
                memory_summary or "<none>",
                "",
                "当前代码片段:",
                code_snippet or "<none>",
                "",
                "当前锚点:",
                f"- 层级: {anchor.level}",
                f"- 对象: {anchor_target}",
                "",
                "局部结构:",
                f"- 所属文件: {file_info}",
                f"- 所属模块: {module_info}",
                "",
                "相关对象:",
                *(related_object_lines or ["- <none>"]),
                "",
                "局部关系:",
                f"- 调用者: {', '.join(callers) if callers else '<none>'}",
                f"- 被调用者: {', '.join(callees) if callees else '<none>'}",
                *(relation_lines or ["- 关系明细: <none>"]),
                "",
                "回答要求:",
                "请基于以上上下文回答问题，如果信息不足请说明。",
            ]
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 2

    @staticmethod
    def _load_code_snippet(selection: CodeSelection | None) -> str:
        if not selection:
            return ""
        path = Path(selection.file_path)
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8").splitlines()
        snippet = lines[selection.line_start - 1 : selection.line_end]
        return "\n".join(snippet)

    @staticmethod
    def _describe_object(object_: Module | File | Symbol) -> str:
        summary = object_.summary or "<no summary>"
        if isinstance(object_, Module):
            return f"- 模块 {object_.id}: {object_.name} ({object_.path}) - {summary}"
        if isinstance(object_, File):
            return f"- 文件 {object_.id}: {object_.path} ({object_.language}) - {summary}"
        return (
            f"- 符号 {object_.id}: {object_.qualified_name} "
            f"[{object_.type}] {object_.signature} - {summary}"
        )

    @staticmethod
    def _describe_relation(relation: Relation) -> str:
        summary = f" - {relation.summary}" if relation.summary else ""
        return f"- 关系 {relation.id}: {relation.source_id} --{relation.relation_type}--> {relation.target_id}{summary}"

    @staticmethod
    def _describe_file(current_object, retrieval_result: RetrievalResult) -> str:
        if isinstance(current_object, File):
            return f"{current_object.path} ({current_object.language})"
        for obj in retrieval_result.related_objects:
            if isinstance(obj, File):
                return f"{obj.path} ({obj.language})"
        return "<unknown>"

    @staticmethod
    def _describe_module(current_object, retrieval_result: RetrievalResult) -> str:
        if isinstance(current_object, Module):
            return current_object.name
        if isinstance(current_object, (File, Symbol)):
            module_id = current_object.module_id
            for obj in retrieval_result.related_objects:
                if isinstance(obj, Module) and obj.id == module_id:
                    return obj.name
        for obj in retrieval_result.related_objects:
            if isinstance(obj, Module):
                return obj.name
        return "<unknown>"
