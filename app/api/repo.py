"""Repository indexing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_graph_repository
from app.core.config import settings
from app.models.qa_models import RepoBuildRequest, RepoBuildResponse, SummaryResponse
from app.services.cleanarch.graph_builder import GraphBuilder
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.storage.vector_store import VectorStore

router = APIRouter(prefix="/repo", tags=["repo"])


@router.post("/build-index", response_model=RepoBuildResponse)
def build_index(request: RepoBuildRequest) -> RepoBuildResponse:
    """Build and persist a repository index."""

    try:
        repository = get_graph_repository()
        repository.initialize_schema()
        graph_builder = GraphBuilder()
        if repository.engine.dialect.name == "postgresql":
            repository.init_vector_tables()
            graph_builder = GraphBuilder(
                embedding_builder=EmbeddingBuilder(),
                vector_store=VectorStore(settings.DATABASE_URL),
            )

        graph = graph_builder.build_graph(repo_path=request.repo_path, branch=request.branch)
        repository.save_graphcode(graph)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RepoBuildResponse(build_id=graph.repo_meta.repo_id, status="success")


@router.post("/scan", response_model=RepoBuildResponse)
def scan_repo(request: RepoBuildRequest) -> RepoBuildResponse:
    """Alias for building and persisting a repository index."""

    return build_index(request)


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
