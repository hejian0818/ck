"""Tests for QA context building."""

from __future__ import annotations

import unittest

from app.models.anchor import Anchor
from app.models.graph_objects import Module, Relation, Symbol
from app.models.qa_models import RetrievalResult
from app.services.context.context_builder import ContextBuilder


class ContextBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = ContextBuilder()
        self.anchor = Anchor(
            level="symbol",
            source="explicit_span",
            confidence=0.9,
            module_id="M_core",
            symbol_id="S_current",
        )
        self.current = Symbol(
            id="S_current",
            name="current",
            qualified_name="core.current",
            type="function",
            signature="current()",
            file_id="F_core",
            module_id="M_core",
            start_line=1,
            end_line=3,
            visibility="public",
            doc="",
        )
        self.module = Module(
            id="M_core",
            name="core",
            path="core",
            summary="Core module.",
            metadata={},
        )

    def test_build_context_includes_memory_summary_and_answer_requirements(self) -> None:
        context = self.builder.build_context(
            question="这个函数做什么？",
            selection=None,
            anchor=self.anchor,
            retrieval_result=RetrievalResult(
                anchor=self.anchor,
                current_object=self.current,
                related_objects=[self.module],
            ),
            memory_summary="S_current:0.92",
        )

        self.assertIn("会话状态摘要:\nS_current:0.92", context)
        self.assertTrue(context.endswith("请基于以上上下文回答问题，如果信息不足请说明。"))

    def test_build_context_trims_related_objects_and_relations_first(self) -> None:
        related = [
            Symbol(
                id=f"S_related_{index}",
                name=f"related_{index}",
                qualified_name=f"core.related_{index}",
                type="function",
                signature=f"related_{index}()",
                file_id="F_core",
                module_id="M_core",
                summary="很长的摘要" * 20,
                start_line=10 + index,
                end_line=11 + index,
                visibility="public",
                doc="",
            )
            for index in range(5)
        ]
        relations = [
            Relation(
                id=f"R_{index}",
                relation_type="calls",
                source_id="S_current",
                target_id=f"S_related_{index}",
                source_type="symbol",
                target_type="symbol",
                source_module_id="M_core",
                target_module_id="M_core",
                summary="很长的关系摘要" * 20,
            )
            for index in range(5)
        ]

        context = self.builder.build_context(
            question="这个函数做什么？",
            selection=None,
            anchor=self.anchor,
            retrieval_result=RetrievalResult(
                anchor=self.anchor,
                current_object=self.current,
                related_objects=related,
                relations=relations,
            ),
            max_context_tokens=120,
        )

        self.assertIn("当前问题: 这个函数做什么？", context)
        self.assertIn("当前代码片段:\n<none>", context)
        self.assertIn("- 对象: S_current", context)
        self.assertIn("相关对象:\n- <none>", context)
        self.assertIn("- 关系明细: <none>", context)
        self.assertNotIn("S_related_0", context)
        self.assertNotIn("R_0", context)


if __name__ == "__main__":
    unittest.main()
