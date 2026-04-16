"""Repository indexing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.dependencies import get_graph_repository
from app.api.errors import handle_api_error, validate_repo_path
from app.core.config import settings
from app.models.qa_models import (
    RepoBuildRequest,
    RepoBuildResponse,
    RepoBuildTaskStatusResponse,
    RepoBuildTaskSubmitResponse,
    SummaryResponse,
)
from app.services.cleanarch.graph_builder import GraphBuilder
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.indexing.task_manager import index_task_manager
from app.storage.vector_store import VectorStore

router = APIRouter(prefix="/repo", tags=["repo"])


@router.post("/build-index", response_model=RepoBuildResponse)
def build_index(request: RepoBuildRequest) -> RepoBuildResponse:
    """Build and persist a repository index."""

    try:
        return _build_and_persist(request)
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


def _build_and_persist(request: RepoBuildRequest) -> RepoBuildResponse:
    repo_path = validate_repo_path(request.repo_path)
    repository = get_graph_repository()
    repository.initialize_schema()
    graph_builder = GraphBuilder()
    if repository.engine.dialect.name == "postgresql":
        repository.init_vector_tables()
        graph_builder = GraphBuilder(
            embedding_builder=EmbeddingBuilder(),
            vector_store=VectorStore(settings.DATABASE_URL),
        )

    previous_graph = None
    if request.incremental:
        previous_repo_id = repository.find_repo_id_by_path(repo_path)
        if previous_repo_id is not None:
            previous_graph = repository.load_graphcode(previous_repo_id)

    file_paths = None
    deleted_paths = None
    if request.changed_only:
        file_paths, deleted_paths = graph_builder.scanner.inspect_changes(repo_path, base_ref=request.base_ref)

    graph = graph_builder.build_graph(
        repo_path=repo_path,
        branch=request.branch,
        previous_graph=previous_graph,
        file_paths=file_paths,
        deleted_paths=deleted_paths,
    )
    repository.save_graphcode(graph)
    return RepoBuildResponse(
        build_id=graph.repo_meta.repo_id,
        status="success",
        **graph_builder.last_build_stats,
    )


@router.post("/scan", response_model=RepoBuildResponse)
def scan_repo(request: RepoBuildRequest) -> RepoBuildResponse:
    """Alias for building and persisting a repository index."""

    return build_index(request)


@router.post("/scan-async", response_model=RepoBuildTaskSubmitResponse)
def scan_repo_async(request: RepoBuildRequest, background_tasks: BackgroundTasks) -> RepoBuildTaskSubmitResponse:
    """Queue a repository index build in the background."""

    try:
        validate_repo_path(request.repo_path)
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)

    task_id = index_task_manager.create_task()
    background_tasks.add_task(_run_index_task, task_id, request)
    return RepoBuildTaskSubmitResponse(task_id=task_id, status="queued")


@router.get("/tasks/{task_id}", response_model=RepoBuildTaskStatusResponse)
def get_index_task(task_id: str) -> RepoBuildTaskStatusResponse:
    """Return background repository index task state."""

    task = index_task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Index task not found")
    return task


def _run_index_task(task_id: str, request: RepoBuildRequest) -> None:
    index_task_manager.mark_running(task_id)
    try:
        result = _build_and_persist(request)
    except Exception as exc:  # pragma: no cover
        index_task_manager.mark_failed(task_id, str(exc))
        return
    index_task_manager.mark_success(task_id, result)


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
