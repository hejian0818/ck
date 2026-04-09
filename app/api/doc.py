"""Document planning and generation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_graph_repository
from app.models.doc_models import DocGenerateRequest, DocPlanRequest, DocumentResult, DocumentSkeleton, SectionPlan
from app.services.agents.doc_agent import DocAgent

router = APIRouter(prefix="/doc", tags=["doc"])


@router.post("/plan", response_model=DocumentSkeleton)
def plan_document(request: DocPlanRequest) -> DocumentSkeleton:
    """Plan a document skeleton for a repository."""

    try:
        agent = DocAgent(repository=get_graph_repository())
        return agent.plan(request.repo_id)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate", response_model=DocumentResult)
def generate_document(request: DocGenerateRequest) -> DocumentResult:
    """Generate a document result from a repository graph."""

    try:
        agent = DocAgent(repository=get_graph_repository())
        return agent.generate(repo_id=request.repo_id, skeleton=request.skeleton)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{repo_id}/sections", response_model=list[SectionPlan])
def list_document_sections(repo_id: str) -> list[SectionPlan]:
    """List planned document sections for a repository."""

    try:
        agent = DocAgent(repository=get_graph_repository())
        return agent.list_sections(repo_id)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
