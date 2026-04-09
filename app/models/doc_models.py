"""Document planning and generation models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SectionPlan(BaseModel):
    """Planned section metadata for a document skeleton."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    level: int
    section_type: Literal["overview", "architecture", "module", "api", "data_flow", "dependency", "summary"]
    target_object_ids: list[str] = Field(default_factory=list)
    description: str


class DocumentSkeleton(BaseModel):
    """Hierarchical section plan for a generated document."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    title: str
    sections: list[SectionPlan] = Field(default_factory=list)


class SectionContent(BaseModel):
    """Generated markdown content for a single section."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    content: str
    diagrams: list[str] = Field(default_factory=list)
    used_objects: list[str] = Field(default_factory=list)
    confidence: float


class DocumentResult(BaseModel):
    """Full generated document payload."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    title: str
    sections: list[SectionContent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocPlanRequest(BaseModel):
    """Request model for document skeleton planning."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str


class DocGenerateRequest(BaseModel):
    """Request model for document generation."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    skeleton: DocumentSkeleton | None = None
