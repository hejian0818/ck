"""Document planning, retrieval, and API tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.doc_models import DocumentResult, DocumentSkeleton, SectionContent, SectionPlan
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.agents.doc_agent import DocAgent, SkeletonPlanner
from app.services.retrieval.doc_retriever import DocRetriever
from app.storage.repositories import GraphRepository


class _DocRepoStub:
    module_app = Module(id="M_app", name="app", path="app", metadata={})
    module_api = Module(id="M_api", name="api", path="api", metadata={})
    file_service = File(
        id="F_service",
        name="service.py",
        path="app/service.py",
        module_id="M_app",
        summary='{"summary":"核心业务服务实现。"}',
        language="python",
        start_line=1,
        end_line=80,
    )
    file_controller = File(
        id="F_controller",
        name="controller.py",
        path="api/controller.py",
        module_id="M_api",
        summary='{"summary":"对外 API 控制器。"}',
        language="python",
        start_line=1,
        end_line=60,
    )
    symbol_service = Symbol(
        id="S_app.Service.run",
        name="run",
        qualified_name="Service.run",
        type="method",
        signature="run(self)",
        file_id="F_service",
        module_id="M_app",
        summary='{"summary":"执行业务主流程。"}',
        start_line=10,
        end_line=30,
        visibility="public",
        doc="",
    )
    symbol_helper = Symbol(
        id="S_app.helper",
        name="helper",
        qualified_name="helper",
        type="function",
        signature="helper()",
        file_id="F_service",
        module_id="M_app",
        summary='{"summary":"补充处理逻辑。"}',
        start_line=35,
        end_line=45,
        visibility="private",
        doc="",
    )
    symbol_controller = Symbol(
        id="S_api.UserController.list_users",
        name="list_users",
        qualified_name="UserController.list_users",
        type="controller",
        signature="list_users()",
        file_id="F_controller",
        module_id="M_api",
        summary='{"summary":"返回用户列表接口。"}',
        start_line=12,
        end_line=25,
        visibility="public",
        doc="",
    )
    relation_cross = Relation(
        id="R_cross",
        relation_type="depends_on",
        source_id="S_api.UserController.list_users",
        target_id="S_app.Service.run",
        source_type="symbol",
        target_type="symbol",
        source_module_id="M_api",
        target_module_id="M_app",
        summary='{"summary":"控制器依赖服务层。"}',
    )
    relation_call = Relation(
        id="R_call",
        relation_type="calls",
        source_id="S_api.UserController.list_users",
        target_id="S_app.Service.run",
        source_type="symbol",
        target_type="symbol",
        source_module_id="M_api",
        target_module_id="M_app",
        summary='{"summary":"控制器调用服务方法。"}',
    )

    def list_modules(self, repo_id: str):  # noqa: ARG002
        return [self.module_app, self.module_api]

    def list_relations(self, repo_id: str):  # noqa: ARG002
        return [self.relation_cross, self.relation_call]

    def list_files_by_module(self, module_id: str):
        if module_id == self.module_app.id:
            return [self.file_service]
        if module_id == self.module_api.id:
            return [self.file_controller]
        return []

    def list_symbols_by_file(self, file_id: str):
        if file_id == self.file_service.id:
            return [self.symbol_service, self.symbol_helper]
        if file_id == self.file_controller.id:
            return [self.symbol_controller]
        return []

    def list_symbols_by_module(self, module_id: str):
        if module_id == self.module_app.id:
            return [self.symbol_service, self.symbol_helper]
        if module_id == self.module_api.id:
            return [self.symbol_controller]
        return []

    def get_module_by_id(self, object_id: str):
        if object_id == self.module_app.id:
            return self.module_app
        if object_id == self.module_api.id:
            return self.module_api
        return None

    def get_file_by_id(self, object_id: str):
        if object_id == self.file_service.id:
            return self.file_service
        if object_id == self.file_controller.id:
            return self.file_controller
        return None

    def get_symbol_by_id(self, object_id: str):
        if object_id == self.symbol_service.id:
            return self.symbol_service
        if object_id == self.symbol_helper.id:
            return self.symbol_helper
        if object_id == self.symbol_controller.id:
            return self.symbol_controller
        return None

    def get_relations_by_source(self, source_id: str):
        return [relation for relation in [self.relation_cross, self.relation_call] if relation.source_id == source_id]

    def get_relations_by_target(self, target_id: str):
        return [relation for relation in [self.relation_cross, self.relation_call] if relation.target_id == target_id]

    def get_relation_by_id(self, relation_id: str):
        for relation in [self.relation_cross, self.relation_call]:
            if relation.id == relation_id:
                return relation
        return None

    def get_repo_path(self, repo_id: str):  # noqa: ARG002
        return "/tmp/sample_repo"


class _DocAgentStub:
    def plan(self, repo_id: str) -> DocumentSkeleton:
        return DocumentSkeleton(
            repo_id=repo_id,
            title="sample_repo Design Document",
            sections=[
                SectionPlan(
                    section_id="overview",
                    title="概述",
                    level=1,
                    section_type="overview",
                    target_object_ids=["M_app"],
                    description="overview",
                )
            ],
        )

    def generate(self, repo_id: str, skeleton: DocumentSkeleton | None = None) -> DocumentResult:
        active_skeleton = skeleton or self.plan(repo_id)
        return DocumentResult(
            repo_id=repo_id,
            title=active_skeleton.title,
            sections=[
                SectionContent(
                    section_id="overview",
                    title="概述",
                    content="overview",
                    used_objects=["M_app"],
                    confidence=0.9,
                )
            ],
            metadata={"section_count": 1},
        )

    def list_sections(self, repo_id: str) -> list[SectionPlan]:
        return self.plan(repo_id).sections


class SkeletonPlannerTests(unittest.TestCase):
    def test_plan_includes_fixed_sections_modules_and_api(self) -> None:
        planner = SkeletonPlanner(_DocRepoStub())

        skeleton = planner.plan("repo_test")

        section_ids = [section.section_id for section in skeleton.sections]
        self.assertEqual(section_ids[0], "overview")
        self.assertEqual(section_ids[1], "architecture")
        self.assertIn("module-M_app", section_ids)
        self.assertIn("module-M_api", section_ids)
        self.assertIn("dependency-analysis", section_ids)
        self.assertIn("api", section_ids)
        self.assertEqual(section_ids[-1], "summary")

        app_module_section = next(section for section in skeleton.sections if section.section_id == "module-M_app")
        self.assertEqual(app_module_section.level, 2)
        self.assertEqual(app_module_section.section_type, "module")

        file_section = next(section for section in skeleton.sections if section.section_id == "file-F_service")
        self.assertEqual(file_section.level, 3)
        self.assertEqual(file_section.target_object_ids, ["F_service"])


class DocRetrieverTests(unittest.TestCase):
    def test_module_section_retrieves_files_and_symbols(self) -> None:
        retriever = DocRetriever(_DocRepoStub())

        result = retriever.retrieve(
            repo_id="repo_test",
            section=SectionPlan(
                section_id="module-M_app",
                title="app",
                level=2,
                section_type="module",
                target_object_ids=["M_app"],
                description="说明 app 模块。",
            ),
        )

        object_ids = [object_.id for object_ in result.objects]
        self.assertIn("M_app", object_ids)
        self.assertIn("F_service", object_ids)
        self.assertIn("S_app.Service.run", object_ids)
        self.assertTrue(result.object_scores)


class DocApiTests(unittest.TestCase):
    def _repository(self) -> GraphRepository:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        return GraphRepository(database_url="sqlite://", engine=engine)

    def test_document_endpoints_return_expected_payloads(self) -> None:
        repository = self._repository()
        with (
            patch("app.api.doc.DocAgent", return_value=_DocAgentStub()),
            patch("app.api.doc.get_graph_repository", return_value=repository),
        ):
            client = TestClient(app)

            plan_response = client.post("/doc/plan", json={"repo_id": "repo_test"})
            generate_response = client.post("/doc/generate", json={"repo_id": "repo_test"})
            sections_response = client.get("/doc/repo_test/sections")
            latest_response = client.get("/doc/repo_test/latest")

        self.assertEqual(plan_response.status_code, 200)
        self.assertEqual(plan_response.json()["title"], "sample_repo Design Document")

        self.assertEqual(generate_response.status_code, 200)
        self.assertEqual(generate_response.json()["metadata"]["section_count"], 1)
        self.assertIn("document_id", generate_response.json()["metadata"])

        self.assertEqual(sections_response.status_code, 200)
        self.assertEqual(sections_response.json()[0]["section_id"], "overview")

        self.assertEqual(latest_response.status_code, 200)
        self.assertEqual(latest_response.json()["repo_id"], "repo_test")
        self.assertEqual(latest_response.json()["sections"][0]["section_id"], "overview")

    def test_doc_agent_generates_markdown_sections(self) -> None:
        agent = DocAgent(
            repository=_DocRepoStub(),
            planner=SkeletonPlanner(_DocRepoStub()),
            retriever=DocRetriever(_DocRepoStub()),
        )

        result = agent.generate("repo_test")

        self.assertTrue(result.sections)
        self.assertIn("关键对象:", result.sections[0].content)


if __name__ == "__main__":
    unittest.main()
