"""Tests for Phase 3 Track 2 document generation flow."""

from __future__ import annotations

import unittest

from app.models.doc_models import DocumentSkeleton, SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.agents.doc_agent import DocAgent, DocLLMClient, SkeletonPlanner
from app.services.retrieval.doc_retriever import DocRetriever


class _RepoStub:
    module_core = Module(
        id="M_core",
        name="core",
        path="app/core",
        summary='{"summary":"核心领域服务。"}',
        metadata={},
    )
    module_api = Module(
        id="M_api",
        name="api",
        path="app/api",
        summary='{"summary":"对外接口层。"}',
        metadata={},
    )
    file_service = File(
        id="F_service",
        name="service.py",
        path="app/core/service.py",
        module_id="M_core",
        summary='{"summary":"服务编排入口。"}',
        language="python",
        start_line=1,
        end_line=80,
    )
    file_repository = File(
        id="F_repository",
        name="repository.py",
        path="app/core/repository.py",
        module_id="M_core",
        summary='{"summary":"仓储接口定义。"}',
        language="python",
        start_line=1,
        end_line=40,
    )
    file_controller = File(
        id="F_controller",
        name="controller.py",
        path="app/api/controller.py",
        module_id="M_api",
        summary='{"summary":"HTTP 控制器。"}',
        language="python",
        start_line=1,
        end_line=60,
    )
    symbol_service = Symbol(
        id="S_core.Service",
        name="Service",
        qualified_name="core.Service",
        type="class",
        signature="class Service",
        file_id="F_service",
        module_id="M_core",
        summary='{"summary":"编排领域逻辑。"}',
        start_line=5,
        end_line=45,
        visibility="public",
        doc="",
    )
    symbol_repository = Symbol(
        id="S_core.Repository",
        name="Repository",
        qualified_name="core.Repository",
        type="interface",
        signature="interface Repository",
        file_id="F_repository",
        module_id="M_core",
        summary='{"summary":"定义持久化访问契约。"}',
        start_line=1,
        end_line=20,
        visibility="public",
        doc="",
    )
    symbol_controller = Symbol(
        id="S_api.UserController.list_users",
        name="list_users",
        qualified_name="api.UserController.list_users",
        type="controller",
        signature="list_users()",
        file_id="F_controller",
        module_id="M_api",
        summary='{"summary":"列出用户接口。"}',
        start_line=10,
        end_line=20,
        visibility="public",
        doc="",
    )
    symbol_run = Symbol(
        id="S_core.Service.run",
        name="run",
        qualified_name="core.Service.run",
        type="method",
        signature="run()",
        file_id="F_service",
        module_id="M_core",
        summary='{"summary":"执行业务主流程。"}',
        start_line=30,
        end_line=40,
        visibility="public",
        doc="",
    )
    relation_dependency = Relation(
        id="R_dep",
        relation_type="depends_on",
        source_id="S_api.UserController.list_users",
        target_id="S_core.Service",
        source_type="symbol",
        target_type="symbol",
        source_module_id="M_api",
        target_module_id="M_core",
        summary='{"summary":"接口层依赖核心服务。"}',
    )
    relation_implements = Relation(
        id="R_impl",
        relation_type="implements",
        source_id="S_core.Service",
        target_id="S_core.Repository",
        source_type="symbol",
        target_type="symbol",
        source_module_id="M_core",
        target_module_id="M_core",
        summary='{"summary":"服务满足仓储契约。"}',
    )
    relation_call_1 = Relation(
        id="R_call_1",
        relation_type="calls",
        source_id="S_api.UserController.list_users",
        target_id="S_core.Service.run",
        source_type="symbol",
        target_type="symbol",
        source_module_id="M_api",
        target_module_id="M_core",
        summary='{"summary":"控制器调用服务入口。"}',
    )
    relation_call_2 = Relation(
        id="R_call_2",
        relation_type="calls",
        source_id="S_core.Service.run",
        target_id="S_core.Repository",
        source_type="symbol",
        target_type="symbol",
        source_module_id="M_core",
        target_module_id="M_core",
        summary='{"summary":"服务读取仓储接口。"}',
    )

    def list_modules(self, repo_id: str):  # noqa: ARG002
        return [self.module_core, self.module_api]

    def list_relations(self, repo_id: str):  # noqa: ARG002
        return [self.relation_dependency, self.relation_implements, self.relation_call_1, self.relation_call_2]

    def list_files_by_module(self, module_id: str):
        if module_id == self.module_core.id:
            return [self.file_service, self.file_repository]
        if module_id == self.module_api.id:
            return [self.file_controller]
        return []

    def list_symbols_by_file(self, file_id: str):
        mapping = {
            self.file_service.id: [self.symbol_service, self.symbol_run],
            self.file_repository.id: [self.symbol_repository],
            self.file_controller.id: [self.symbol_controller],
        }
        return mapping.get(file_id, [])

    def list_symbols_by_module(self, module_id: str):
        mapping = {
            self.module_core.id: [self.symbol_service, self.symbol_repository, self.symbol_run],
            self.module_api.id: [self.symbol_controller],
        }
        return mapping.get(module_id, [])

    def get_module_by_id(self, object_id: str):
        return {
            self.module_core.id: self.module_core,
            self.module_api.id: self.module_api,
        }.get(object_id)

    def get_file_by_id(self, object_id: str):
        return {
            self.file_service.id: self.file_service,
            self.file_repository.id: self.file_repository,
            self.file_controller.id: self.file_controller,
        }.get(object_id)

    def get_symbol_by_id(self, object_id: str):
        return {
            self.symbol_service.id: self.symbol_service,
            self.symbol_repository.id: self.symbol_repository,
            self.symbol_controller.id: self.symbol_controller,
            self.symbol_run.id: self.symbol_run,
        }.get(object_id)

    def get_relations_by_source(self, source_id: str):
        return [relation for relation in self.list_relations("repo_test") if relation.source_id == source_id]

    def get_relations_by_target(self, target_id: str):
        return [relation for relation in self.list_relations("repo_test") if relation.target_id == target_id]

    def get_relation_by_id(self, relation_id: str):
        for relation in self.list_relations("repo_test"):
            if relation.id == relation_id:
                return relation
        return None

    def get_repo_path(self, repo_id: str):  # noqa: ARG002
        return "/tmp/repo_test"


class _LLMStub(DocLLMClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, section: SectionPlan, retrieval, prompt: str) -> str:  # noqa: ANN001
        self.prompts.append(prompt)
        if section.section_id == "summary":
            raise RuntimeError("boom")
        return "\n".join(
            [
                f"本文段覆盖 {section.section_type}。",
                "",
                f"对象数量: {len(retrieval.objects)}",
            ]
        )


class DocAgentPhase3Tests(unittest.TestCase):
    def test_doc_agent_generates_markdown_diagrams_and_non_blocking_failures(self) -> None:
        repo = _RepoStub()
        llm_client = _LLMStub()
        agent = DocAgent(
            repository=repo,
            planner=SkeletonPlanner(repo),
            retriever=DocRetriever(repo),
            llm_client=llm_client,
        )
        skeleton = DocumentSkeleton(
            repo_id="repo_test",
            title="Repo Test Design Document",
            sections=[
                SectionPlan(
                    section_id="overview",
                    title="概述",
                    level=1,
                    section_type="overview",
                    target_object_ids=["M_core", "M_api"],
                    description="总结整体模块。",
                ),
                SectionPlan(
                    section_id="module-core",
                    title="core",
                    level=2,
                    section_type="module",
                    target_object_ids=["M_core"],
                    description="说明核心模块。",
                ),
                SectionPlan(
                    section_id="api",
                    title="API 设计",
                    level=1,
                    section_type="api",
                    target_object_ids=["S_api.UserController.list_users"],
                    description="描述接口调用链。",
                ),
                SectionPlan(
                    section_id="summary",
                    title="总结",
                    level=1,
                    section_type="summary",
                    target_object_ids=["M_core"],
                    description="汇总关键结论。",
                ),
            ],
        )

        result = agent.generate("repo_test", skeleton=skeleton)

        self.assertEqual(result.metadata["section_count"], 4)
        self.assertTrue(result.sections[0].content.startswith("# 概述"))
        self.assertIn("@startuml", result.sections[0].diagrams[0])
        self.assertTrue(result.sections[1].content.startswith("## core"))
        self.assertIn("@startuml", result.sections[1].diagrams[0])
        self.assertIn("@startuml", result.sections[2].diagrams[0])
        self.assertEqual(result.sections[3].confidence, 0.0)
        self.assertIn("生成失败", result.sections[3].content)
        self.assertTrue(any("section_type: api" in prompt for prompt in llm_client.prompts))


if __name__ == "__main__":
    unittest.main()
