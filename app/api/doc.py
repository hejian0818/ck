"""Document planning and generation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_graph_repository, memory_manager, require_api_key, require_rate_limit
from app.api.errors import error_detail, handle_api_error
from app.models.doc_models import DocGenerateRequest, DocPlanRequest, DocumentResult, DocumentSkeleton, SectionPlan
from app.services.agents.doc_agent import DocAgent
from app.services.review.doc_reviewer import DocumentReviewer
from app.services.workflows.doc_graph import DocWorkflow

router = APIRouter(prefix="/doc", tags=["doc"])


@router.post("/plan", response_model=DocumentSkeleton, dependencies=[Depends(require_rate_limit), Depends(require_api_key)])
def plan_document(request: DocPlanRequest) -> DocumentSkeleton:
    """Plan a document skeleton for a repository."""

    try:
        repository = get_graph_repository()
        agent = DocAgent(
            repository=repository,
            memory_manager=memory_manager,
            reviewer=DocumentReviewer(repository),
        )
        skeleton = DocWorkflow(agent).plan(request.repo_id)
        repository.initialize_schema()
        repository.save_document_skeleton(skeleton)
        return skeleton
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


@router.post("/generate", response_model=DocumentResult, dependencies=[Depends(require_rate_limit), Depends(require_api_key)])
def generate_document(request: DocGenerateRequest) -> DocumentResult:
    """Generate a document result from a repository graph."""

    try:
        repository = get_graph_repository()
        agent = DocAgent(
            repository=repository,
            memory_manager=memory_manager,
            reviewer=DocumentReviewer(repository),
        )
        document = DocWorkflow(agent).generate(repo_id=request.repo_id, skeleton=request.skeleton)
        repository.initialize_schema()
        if request.skeleton is not None:
            repository.save_document_skeleton(request.skeleton)
        document_id = repository.save_document_result(document)
        metadata = dict(document.metadata)
        metadata.setdefault("document_id", document_id)
        return document.model_copy(update={"metadata": metadata})
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


@router.get("/{repo_id}/latest", response_model=DocumentResult)
def get_latest_document(repo_id: str) -> DocumentResult:
    """Return the latest persisted generated document for a repository."""

    try:
        repository = get_graph_repository()
        repository.initialize_schema()
        document = repository.get_latest_document_result(repo_id)
        if document is None:
            raise HTTPException(
                status_code=404,
                detail=error_detail("document_not_found", "Generated document not found"),
            )
        return document
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


@router.get("/{repo_id}/sections", response_model=list[SectionPlan])
def list_document_sections(repo_id: str) -> list[SectionPlan]:
    """List planned document sections for a repository."""

    try:
        repository = get_graph_repository()
        repository.initialize_schema()
        persisted_skeleton = repository.get_document_skeleton(repo_id)
        if persisted_skeleton is not None:
            return persisted_skeleton.sections
        agent = DocAgent(
            repository=repository,
            memory_manager=memory_manager,
            reviewer=DocumentReviewer(repository),
        )
        return agent.list_sections(repo_id)
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)
