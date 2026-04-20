"""LangGraph workflow integration tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.models.anchor import Anchor
from app.models.doc_models import DocumentResult, DocumentSkeleton, SectionContent, SectionPlan
from app.models.qa_models import QAResponse, RepoBuildRequest
from app.services.agents.metrics import Metrics
from app.services.workflows.doc_graph import DocWorkflow
from app.services.workflows.qa_graph import QAWorkflow
from app.services.workflows.repo_index_graph import RepoIndexWorkflow
from app.storage.repositories import GraphRepository


class _QAAgentStub:
    def __init__(self) -> None:
        self.calls = 0

    def answer(self, repo_id, question, selection, session_id):  # noqa: ANN001, ANN201
        self.calls += 1
        return QAResponse(
            answer=f"{repo_id}:{question}:{session_id}",
            anchor=Anchor(level="module", source="name_match", module_id=repo_id, confidence=0.9),
            confidence=0.9,
            need_more_context=False,
            metrics=Metrics(),
        )


class _DocAgentStub:
    def __init__(self) -> None:
        self.plan_calls = 0
        self.generate_calls = 0

    def plan(self, repo_id):  # noqa: ANN001, ANN201
        self.plan_calls += 1
        return _skeleton(repo_id)

    def generate(self, repo_id, skeleton=None):  # noqa: ANN001, ANN201
        self.generate_calls += 1
        active_skeleton = skeleton or _skeleton(repo_id)
        return DocumentResult(
            repo_id=repo_id,
            title=active_skeleton.title,
            sections=[
                SectionContent(
                    section_id="overview",
                    title="概述",
                    content="content",
                    confidence=1.0,
                )
            ],
        )


def _skeleton(repo_id: str) -> DocumentSkeleton:
    return DocumentSkeleton(
        repo_id=repo_id,
        title="Test Doc",
        sections=[
            SectionPlan(
                section_id="overview",
                title="概述",
                level=1,
                section_type="overview",
                description="overview",
            )
        ],
    )


class LangGraphWorkflowTests(unittest.TestCase):
    def test_qa_workflow_invokes_agent_through_langgraph(self) -> None:
        agent = _QAAgentStub()

        with patch("app.services.workflows.qa_graph.settings.LANGGRAPH_ENABLED", True):
            response = QAWorkflow(agent).answer(
                repo_id="repo",
                question="question",
                selection=None,
                session_id="session",
            )

        self.assertEqual(response.answer, "repo:question:session")
        self.assertEqual(agent.calls, 1)

    def test_doc_workflow_plans_without_generating_for_plan_call(self) -> None:
        agent = _DocAgentStub()

        with patch("app.services.workflows.doc_graph.settings.LANGGRAPH_ENABLED", True):
            skeleton = DocWorkflow(agent).plan("repo")

        self.assertEqual(skeleton.repo_id, "repo")
        self.assertEqual(agent.plan_calls, 1)
        self.assertEqual(agent.generate_calls, 0)

    def test_doc_workflow_generates_with_planned_skeleton(self) -> None:
        agent = _DocAgentStub()

        with patch("app.services.workflows.doc_graph.settings.LANGGRAPH_ENABLED", True):
            document = DocWorkflow(agent).generate(repo_id="repo", skeleton=_skeleton("repo"))

        self.assertEqual(document.repo_id, "repo")
        self.assertEqual(agent.generate_calls, 1)

    def test_qa_workflow_can_be_disabled(self) -> None:
        agent = _QAAgentStub()

        with patch("app.services.workflows.qa_graph.settings.LANGGRAPH_ENABLED", False):
            response = QAWorkflow(agent).answer(
                repo_id="repo",
                question="question",
                selection=None,
                session_id="session",
            )

        self.assertEqual(response.answer, "repo:question:session")
        self.assertEqual(agent.calls, 1)

    def test_repo_index_workflow_builds_and_persists_through_langgraph(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        repository = GraphRepository(database_url="sqlite://", engine=engine)

        with patch("app.services.workflows.repo_index_graph.settings.LANGGRAPH_ENABLED", True):
            response = RepoIndexWorkflow(repository).build(
                RepoBuildRequest(repo_path=str(Path("data/test_repo").resolve()), branch="main")
            )

        self.assertEqual(response.status, "success")
        self.assertTrue(repository.list_modules(response.build_id))
        self.assertGreaterEqual(response.parsed_files, 1)


if __name__ == "__main__":
    unittest.main()
