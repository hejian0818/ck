"""QA and session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_graph_repository, memory_manager, require_api_key, require_rate_limit
from app.api.errors import handle_api_error
from app.models.qa_models import QAAskRequest, QAResponse, SessionStateResponse
from app.services.agents.qa_agent import QAAgent
from app.services.workflows.qa_graph import QAWorkflow

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/ask", response_model=QAResponse, dependencies=[Depends(require_rate_limit), Depends(require_api_key)])
def ask_question(request: QAAskRequest) -> QAResponse:
    """Answer a code question."""

    try:
        agent = QAAgent(repository=get_graph_repository(), memory_manager=memory_manager)
        workflow = QAWorkflow(agent)
        return workflow.answer(
            repo_id=request.repo_id,
            question=request.question,
            selection=request.selection,
            session_id=request.session_id,
        )
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


@router.get("/session/{session_id}", response_model=SessionStateResponse)
def get_session_state(session_id: str) -> SessionStateResponse:
    """Return current session anchor state."""

    memory = memory_manager.get_anchor_memory(session_id)
    return SessionStateResponse(session_id=session_id, current_anchor=memory.current_anchor)


@router.post(
    "/session/{session_id}/reset",
    response_model=SessionStateResponse,
    dependencies=[Depends(require_rate_limit), Depends(require_api_key)],
)
def reset_session(session_id: str) -> SessionStateResponse:
    """Clear session memory."""

    memory_manager.clear_memory(session_id)
    return SessionStateResponse(session_id=session_id, current_anchor=None)
