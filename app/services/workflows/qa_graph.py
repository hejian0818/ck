"""LangGraph workflow for code QA."""

from __future__ import annotations

from typing import TypedDict

from app.core.config import settings
from app.models.qa_models import CodeSelection, QAResponse
from app.services.agents.qa_agent import QAAgent
from app.services.workflows.checkpoint import get_langgraph_checkpointer


class QAWorkflowState(TypedDict, total=False):
    """State carried by the QA LangGraph workflow."""

    repo_id: str
    question: str
    selection: CodeSelection | None
    session_id: str
    response: QAResponse


class QAWorkflow:
    """Execute QA through a LangGraph state graph."""

    def __init__(self, agent: QAAgent) -> None:
        self.agent = agent
        self.graph = self._compile_graph()

    def answer(
        self,
        *,
        repo_id: str,
        question: str,
        selection: CodeSelection | None,
        session_id: str,
    ) -> QAResponse:
        if not settings.LANGGRAPH_ENABLED:
            return self.agent.answer(
                repo_id=repo_id,
                question=question,
                selection=selection,
                session_id=session_id,
            )

        final_state = self.graph.invoke(
            {
                "repo_id": repo_id,
                "question": question,
                "selection": selection,
                "session_id": session_id,
            },
            config={"configurable": {"thread_id": f"qa:{repo_id}:{session_id}"}},
        )
        return final_state["response"]

    def _compile_graph(self):
        from langgraph.graph import END, START, StateGraph

        workflow = StateGraph(QAWorkflowState)
        workflow.add_node("answer", self._answer_node)
        workflow.add_edge(START, "answer")
        workflow.add_edge("answer", END)
        return workflow.compile(checkpointer=get_langgraph_checkpointer())

    def _answer_node(self, state: QAWorkflowState) -> QAWorkflowState:
        response = self.agent.answer(
            repo_id=state["repo_id"],
            question=state["question"],
            selection=state.get("selection"),
            session_id=state["session_id"],
        )
        return {"response": response}
