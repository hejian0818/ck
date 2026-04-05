"""Repository indexing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_graph_repository
from app.models.qa_models import RepoBuildRequest, RepoBuildResponse, SummaryResponse
from app.services.cleanarch.graph_builder import GraphBuilder

router = APIRouter(prefix="/repo", tags=["repo"])


@router.post("/build-index", response_model=RepoBuildResponse)
def build_index(request: RepoBuildRequest) -> RepoBuildResponse:
    """Build and persist a repository index."""

    try:
        graph = GraphBuilder().build_graph(repo_path=request.repo_path, branch=request.branch)
        repository = get_graph_repository()
        repository.initialize_schema()
        repository.save_graphcode(graph)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RepoBuildResponse(build_id=graph.repo_meta.repo_id, status="success")


@router.get("/{object_type}/{object_id}/summary", response_model=SummaryResponse)
def get_object_summary(object_type: str, object_id: str) -> SummaryResponse:
    """Fetch a persisted summary for a graph object."""

    repository = get_graph_repository()
    try:
        summary = repository.get_summary(object_type, object_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")

    return SummaryResponse(object_type=object_type, object_id=object_id, summary=summary)
