"""Shared QA request and response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.anchor import Anchor
from app.models.graph_objects import File, Module, Relation, Symbol
from app.services.agents.metrics import Metrics


class CodeSelection(BaseModel):
    """User-selected source range."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    line_start: int
    line_end: int


GraphObject = Module | File | Symbol


class RetrievalResult(BaseModel):
    """Structured retrieval result for QA."""

    model_config = ConfigDict(extra="forbid")

    anchor: Anchor
    current_object: GraphObject | None = None
    related_objects: list[GraphObject] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    object_scores: dict[str, float] = Field(default_factory=dict)


class QAResponse(BaseModel):
    """QA agent response."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    anchor: Anchor
    confidence: float
    used_objects: list[str] = Field(default_factory=list)
    need_more_context: bool
    strategy_used: str = "S4"
    metrics: Metrics = Field(default_factory=Metrics)
    degraded: bool = False
    suggestions: list[str] = Field(default_factory=list)


class RepoBuildRequest(BaseModel):
    """Request to build a repository index."""

    model_config = ConfigDict(extra="forbid")

    repo_path: str
    branch: str = "main"


class RepoBuildResponse(BaseModel):
    """Response for index build."""

    model_config = ConfigDict(extra="forbid")

    build_id: str
    status: Literal["success"]


class SummaryResponse(BaseModel):
    """Response model for summary lookup."""

    model_config = ConfigDict(extra="forbid")

    object_type: Literal["module", "file", "symbol", "relation"]
    object_id: str
    summary: str


class QAAskRequest(BaseModel):
    """Request model for QA endpoint."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    session_id: str
    question: str
    selection: CodeSelection | None = None


class SessionStateResponse(BaseModel):
    """Session state response."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    current_anchor: Anchor | None = None
