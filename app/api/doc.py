"""Document planning and generation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_graph_repository, memory_manager, require_api_key
from app.api.errors import handle_api_error
from app.models.doc_models import DocGenerateRequest, DocPlanRequest, DocumentResult, DocumentSkeleton, SectionPlan
from app.services.agents.doc_agent import DocAgent
from app.services.review.doc_reviewer import DocumentReviewer
from app.services.workflows.doc_graph import DocWorkflow

router = APIRouter(prefix="/doc", tags=["doc"])


@router.post("/plan", response_model=DocumentSkeleton, dependencies=[Depends(require_api_key)])
def plan_document(request: DocPlanRequest) -> DocumentSkeleton:
    """Plan a document skeleton for a repository."""

    try:
        repository = get_graph_repository()
        agent = DocAgent(
            repository=repository,
            memory_manager=memory_manager,
            reviewer=DocumentReviewer(repository),
        )
        return DocWorkflow(agent).plan(request.repo_id)
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


@router.post("/generate", response_model=DocumentResult, dependencies=[Depends(require_api_key)])
def generate_document(request: DocGenerateRequest) -> DocumentResult:
    """Generate a document result from a repository graph."""

    try:
        repository = get_graph_repository()
        agent = DocAgent(
            repository=repository,
            memory_manager=memory_manager,
            reviewer=DocumentReviewer(repository),
        )
        return DocWorkflow(agent).generate(repo_id=request.repo_id, skeleton=request.skeleton)
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


@router.get("/{repo_id}/sections", response_model=list[SectionPlan])
def list_document_sections(repo_id: str) -> list[SectionPlan]:
    """List planned document sections for a repository."""

    try:
        repository = get_graph_repository()
        agent = DocAgent(
            repository=repository,
            memory_manager=memory_manager,
            reviewer=DocumentReviewer(repository),
        )
        return agent.list_sections(repo_id)
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)
