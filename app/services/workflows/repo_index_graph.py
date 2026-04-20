"""LangGraph workflow for repository indexing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from fastapi import HTTPException

from app.api.errors import error_detail, validate_repo_path
from app.core.config import settings
from app.models.graph_objects import GraphCode
from app.models.qa_models import RepoBuildRequest, RepoBuildResponse
from app.services.cleanarch.graph_builder import GraphBuilder
from app.services.indexing.embedding_builder import EmbeddingBuilder
from app.services.locks.distributed_lock import redis_lock
from app.services.workflows.checkpoint import get_langgraph_checkpointer
from app.storage.repositories import GraphRepository
from app.storage.vector_store import VectorStore


class RepoIndexWorkflowState(TypedDict, total=False):
    """State carried by the repository indexing LangGraph workflow."""

    request: RepoBuildRequest
    repo_path: str
    use_vector_indexing: bool
    previous_graph: GraphCode | None
    file_paths: list[str] | None
    deleted_paths: list[str] | None
    graph: GraphCode
    build_stats: dict[str, Any]
    response: RepoBuildResponse


class RepoIndexWorkflow:
    """Build and persist repository indexes through a LangGraph state graph."""

    def __init__(
        self,
        repository: GraphRepository,
        graph_builder_factory: Callable[..., GraphBuilder] = GraphBuilder,
    ) -> None:
        self.repository = repository
        self.graph_builder_factory = graph_builder_factory
        self.graph = self._compile_graph()

    def build(self, request: RepoBuildRequest) -> RepoBuildResponse:
        repo_path = validate_repo_path(request.repo_path)
        with redis_lock(f"repo-index:{repo_path}") as acquired:
            if not acquired:
                raise HTTPException(
                    status_code=409,
                    detail=error_detail("repo_index_in_progress", "Repository indexing is already running"),
                )
            if not settings.LANGGRAPH_ENABLED:
                return self._run_direct(request=request, repo_path=repo_path)

            final_state = self.graph.invoke(
                {"request": request, "repo_path": repo_path},
                config={"configurable": {"thread_id": f"repo-index:{repo_path}:{request.branch}"}},
            )
            return final_state["response"]

    def _compile_graph(self):
        from langgraph.graph import END, START, StateGraph

        workflow = StateGraph(RepoIndexWorkflowState)
        workflow.add_node("prepare_repository", self._prepare_repository_node)
        workflow.add_node("load_previous_graph", self._load_previous_graph_node)
        workflow.add_node("inspect_changes", self._inspect_changes_node)
        workflow.add_node("build_graph", self._build_graph_node)
        workflow.add_node("persist_graph", self._persist_graph_node)
        workflow.add_node("build_response", self._build_response_node)
        workflow.add_edge(START, "prepare_repository")
        workflow.add_edge("prepare_repository", "load_previous_graph")
        workflow.add_edge("load_previous_graph", "inspect_changes")
        workflow.add_edge("inspect_changes", "build_graph")
        workflow.add_edge("build_graph", "persist_graph")
        workflow.add_edge("persist_graph", "build_response")
        workflow.add_edge("build_response", END)
        return workflow.compile(checkpointer=get_langgraph_checkpointer())

    def _run_direct(self, *, request: RepoBuildRequest, repo_path: str) -> RepoBuildResponse:
        state: RepoIndexWorkflowState = {"request": request, "repo_path": repo_path}
        state.update(self._prepare_repository_node(state))
        state.update(self._load_previous_graph_node(state))
        state.update(self._inspect_changes_node(state))
        state.update(self._build_graph_node(state))
        state.update(self._persist_graph_node(state))
        state.update(self._build_response_node(state))
        return state["response"]

    def _prepare_repository_node(self, state: RepoIndexWorkflowState) -> RepoIndexWorkflowState:
        self.repository.initialize_schema()
        use_vector_indexing = self.repository.engine.dialect.name == "postgresql" and settings.ENABLE_VECTOR_INDEXING
        if use_vector_indexing:
            self.repository.init_vector_tables()
        return {"use_vector_indexing": use_vector_indexing}

    def _load_previous_graph_node(self, state: RepoIndexWorkflowState) -> RepoIndexWorkflowState:
        request = state["request"]
        if not request.incremental:
            return {"previous_graph": None}
        previous_repo_id = self.repository.find_repo_id_by_path(state["repo_path"])
        if previous_repo_id is None:
            return {"previous_graph": None}
        return {"previous_graph": self.repository.load_graphcode(previous_repo_id)}

    def _inspect_changes_node(self, state: RepoIndexWorkflowState) -> RepoIndexWorkflowState:
        request = state["request"]
        if not request.changed_only:
            return {"file_paths": None, "deleted_paths": None}
        graph_builder = self.graph_builder_factory()
        file_paths, deleted_paths = graph_builder.scanner.inspect_changes(state["repo_path"], base_ref=request.base_ref)
        return {"file_paths": file_paths, "deleted_paths": deleted_paths}

    def _build_graph_node(self, state: RepoIndexWorkflowState) -> RepoIndexWorkflowState:
        request = state["request"]
        graph_builder = self._make_graph_builder(bool(state.get("use_vector_indexing")))
        graph = graph_builder.build_graph(
            repo_path=state["repo_path"],
            branch=request.branch,
            previous_graph=state.get("previous_graph"),
            file_paths=state.get("file_paths"),
            deleted_paths=state.get("deleted_paths"),
        )
        return {"graph": graph, "build_stats": dict(graph_builder.last_build_stats)}

    def _persist_graph_node(self, state: RepoIndexWorkflowState) -> RepoIndexWorkflowState:
        self.repository.save_graphcode(state["graph"])
        return {}

    def _build_response_node(self, state: RepoIndexWorkflowState) -> RepoIndexWorkflowState:
        graph = state["graph"]
        return {
            "response": RepoBuildResponse(
                build_id=graph.repo_meta.repo_id,
                status="success",
                **state["build_stats"],
            )
        }

    def _make_graph_builder(self, use_vector_indexing: bool) -> GraphBuilder:
        if not use_vector_indexing:
            return self.graph_builder_factory()
        return self.graph_builder_factory(
            embedding_builder=EmbeddingBuilder(),
            vector_store=VectorStore(settings.DATABASE_URL),
        )
