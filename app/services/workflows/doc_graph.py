"""LangGraph workflow for document planning and generation."""

from __future__ import annotations

from typing import TypedDict

from app.core.config import settings
from app.models.doc_models import DocumentResult, DocumentSkeleton
from app.services.agents.doc_agent import DocAgent
from app.services.workflows.checkpoint import get_langgraph_checkpointer


class DocWorkflowState(TypedDict, total=False):
    """State carried by the document LangGraph workflow."""

    repo_id: str
    mode: str
    skeleton: DocumentSkeleton | None
    planned_skeleton: DocumentSkeleton
    document: DocumentResult


class DocWorkflow:
    """Execute document planning and generation through LangGraph."""

    def __init__(self, agent: DocAgent) -> None:
        self.agent = agent
        self.graph = self._compile_graph()

    def plan(self, repo_id: str) -> DocumentSkeleton:
        if not settings.LANGGRAPH_ENABLED:
            return self.agent.plan(repo_id)
        state = self.graph.invoke(
            {"repo_id": repo_id, "mode": "plan", "skeleton": None},
            config={"configurable": {"thread_id": f"doc-plan:{repo_id}"}},
        )
        return state["planned_skeleton"]

    def generate(self, *, repo_id: str, skeleton: DocumentSkeleton | None) -> DocumentResult:
        if not settings.LANGGRAPH_ENABLED:
            return self.agent.generate(repo_id=repo_id, skeleton=skeleton)
        state = self.graph.invoke(
            {"repo_id": repo_id, "mode": "generate", "skeleton": skeleton},
            config={"configurable": {"thread_id": f"doc-generate:{repo_id}"}},
        )
        return state["document"]

    def _compile_graph(self):
        from langgraph.graph import END, START, StateGraph

        workflow = StateGraph(DocWorkflowState)
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_edge(START, "plan")
        workflow.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {
                "generate": "generate",
                "end": END,
            },
        )
        workflow.add_edge("generate", END)
        return workflow.compile(checkpointer=get_langgraph_checkpointer())

    def _plan_node(self, state: DocWorkflowState) -> DocWorkflowState:
        skeleton = state.get("skeleton") or self.agent.plan(state["repo_id"])
        return {"planned_skeleton": skeleton}

    @staticmethod
    def _route_after_plan(state: DocWorkflowState) -> str:
        return "generate" if state.get("mode") == "generate" else "end"

    def _generate_node(self, state: DocWorkflowState) -> DocWorkflowState:
        document = self.agent.generate(repo_id=state["repo_id"], skeleton=state["planned_skeleton"])
        return {"document": document}
