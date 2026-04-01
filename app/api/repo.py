"""Repository indexing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_graph_repository
from app.models.qa_models import RepoBuildRequest, RepoBuildResponse
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
