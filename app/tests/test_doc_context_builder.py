"""Tests for document section context building."""

from __future__ import annotations

import unittest

from app.models.doc_models import SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.context.doc_context_builder import DocContextBuilder
from app.services.retrieval.doc_retriever import SectionRetrievalResult


class DocContextBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = DocContextBuilder()
        self.module = Module(
            id="M_core",
            name="core",
            path="app/core",
            summary='{"summary":"核心业务模块。"}',
            metadata={},
        )
        self.file = File(
            id="F_service",
            name="service.py",
            path="app/core/service.py",
            module_id="M_core",
            summary='{"summary":"核心服务实现。"}',
            language="python",
            start_line=1,
            end_line=80,
        )
        self.symbol = Symbol(
            id="S_core.Service",
            name="Service",
            qualified_name="core.Service",
            type="class",
            signature="class Service",
            file_id="F_service",
            module_id="M_core",
            summary='{"summary":"统一调度核心流程。"}',
            start_line=5,
            end_line=40,
            visibility="public",
            doc="",
        )
        self.relation = Relation(
            id="R_dep",
            relation_type="depends_on",
            source_id="M_api",
            target_id="M_core",
            source_type="module",
            target_type="module",
            source_module_id="M_api",
            target_module_id="M_core",
            summary='{"summary":"API 模块依赖核心服务。"}',
        )

    def test_build_context_uses_overview_template_and_prioritizes_high_score_objects(self) -> None:
        section = SectionPlan(
            section_id="overview",
            title="概述",
            level=1,
            section_type="overview",
            target_object_ids=["M_core"],
            description="总结整体架构。",
        )
        retrieval = SectionRetrievalResult(
            section=section,
            objects=[self.file, self.module, self.symbol],
            relations=[self.relation],
            object_scores={
                self.file.id: 0.4,
                self.module.id: 0.9,
                self.symbol.id: 0.6,
            },
        )

        prompt = self.builder.build_context(section, retrieval)

        self.assertIn("输出要求:", prompt)
        self.assertIn("- 概括仓库目标、主要模块和整体协作方式。", prompt)
        self.assertIn("段落标题使用 `# 概述`", prompt)
        self.assertLess(prompt.index("模块 `core`"), prompt.index("文件 `app/core/service.py`"))

    def test_build_context_uses_api_template(self) -> None:
        section = SectionPlan(
            section_id="api",
            title="API 设计",
            level=1,
            section_type="api",
            target_object_ids=["S_core.Service"],
            description="说明对外接口。",
        )
        retrieval = SectionRetrievalResult(
            section=section,
            objects=[self.symbol],
            relations=[self.relation],
            object_scores={self.symbol.id: 0.8},
        )

        prompt = self.builder.build_context(section, retrieval)

        self.assertIn("- 描述对外接口、请求处理入口和核心调用链。", prompt)
        self.assertIn("符号 `core.Service`", prompt)


if __name__ == "__main__":
    unittest.main()
