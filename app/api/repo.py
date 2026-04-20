"""Repository indexing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import get_graph_repository, require_api_key, require_rate_limit
from app.api.errors import error_detail, handle_api_error, validate_repo_path
from app.models.qa_models import (
    RepoBuildRequest,
    RepoBuildResponse,
    RepoBuildTaskListResponse,
    RepoBuildTaskStatusResponse,
    RepoBuildTaskSubmitResponse,
    SummaryResponse,
)
from app.services.indexing.task_manager import index_task_manager
from app.services.workflows.repo_index_graph import RepoIndexWorkflow

router = APIRouter(prefix="/repo", tags=["repo"])


@router.post("/build-index", response_model=RepoBuildResponse, dependencies=[Depends(require_rate_limit), Depends(require_api_key)])
def build_index(request: RepoBuildRequest) -> RepoBuildResponse:
    """Build and persist a repository index."""

    try:
        return _build_and_persist(request)
    except Exception as exc:  # pragma: no cover
        handle_api_error(exc)


def _build_and_persist(request: RepoBuildRequest) -> RepoBuildResponse:
    return RepoIndexWorkflow(get_graph_repository()).build(request)


@router.post("/scan", response_model=RepoBuildResponse, dependencies=[Depends(require_rate_limit), Depends(require_api_key)])
def scan_repo(request: RepoBuildRequest) -> RepoBuildResponse:
    """Alias for building and persisting a repository index."""

    return build_index(request)


@router.post("/scan-async", response_model=RepoBuildTaskSubmitResponse, dependencies=[Depends(require_rate_limit), Depends(require_api_key)])
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
        raise HTTPException(status_code=404, detail=error_detail("task_not_found", "Index task not found"))
    return task


@router.get("/tasks", response_model=RepoBuildTaskListResponse)
def list_index_tasks(status: str | None = None, limit: int = 50) -> RepoBuildTaskListResponse:
    """Return recent background repository index tasks."""

    if status is not None and status not in {"queued", "running", "success", "failed"}:
        raise HTTPException(status_code=400, detail=error_detail("bad_request", "Invalid task status filter"))
    if limit < 0:
        raise HTTPException(status_code=400, detail=error_detail("bad_request", "Task list limit must be non-negative"))
    return RepoBuildTaskListResponse(tasks=index_task_manager.list_tasks(status=status, limit=limit))


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
        raise HTTPException(status_code=400, detail=error_detail("bad_request", str(exc))) from exc

    if summary is None:
        raise HTTPException(status_code=404, detail=error_detail("summary_not_found", "Summary not found"))

    return SummaryResponse(object_type=object_type, object_id=object_id, summary=summary)
