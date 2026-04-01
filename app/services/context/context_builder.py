"""Build LLM-ready QA context."""

from __future__ import annotations

from pathlib import Path

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Symbol
from app.models.qa_models import CodeSelection, RetrievalResult


class ContextBuilder:
    """Assemble a structured text context for QA."""

    def build_context(
        self,
        question: str,
        selection: CodeSelection | None,
        anchor: Anchor,
        retrieval_result: RetrievalResult,
    ) -> str:
        code_snippet = self._load_code_snippet(selection)
        current_object = retrieval_result.current_object
        file_info = self._describe_file(current_object, retrieval_result)
        module_info = self._describe_module(current_object, retrieval_result)
        callers = [
            relation.source_id
            for relation in retrieval_result.relations
            if anchor.symbol_id and relation.target_id == anchor.symbol_id
        ]
        callees = [
            relation.target_id
            for relation in retrieval_result.relations
            if anchor.symbol_id and relation.source_id == anchor.symbol_id
        ]
        anchor_target = anchor.symbol_id or anchor.file_id or anchor.module_id or "none"

        return "\n".join(
            [
                f"当前问题: {question}",
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
                "局部关系:",
                f"- 调用者: {', '.join(callers) if callers else '<none>'}",
                f"- 被调用者: {', '.join(callees) if callees else '<none>'}",
                "",
                "请回答上述问题。",
            ]
        )

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
