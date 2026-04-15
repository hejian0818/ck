"""Core graph objects for repository indexing."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RepoMeta(BaseModel):
    """Repository metadata captured during scanning."""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    repo_path: str
    branch: str
    commit_hash: str
    scan_time: datetime


class Module(BaseModel):
    """Logical module within a repository."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    path: str
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class File(BaseModel):
    """Source file within a module."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    path: str
    module_id: str
    summary: str = ""
    content_hash: str = ""
    language: str
    start_line: int
    end_line: int


class Symbol(BaseModel):
    """Code symbol parsed from a source file."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    qualified_name: str
    type: str
    signature: str
    file_id: str
    module_id: str
    summary: str = ""
    start_line: int
    end_line: int
    visibility: str
    doc: str


class Relation(BaseModel):
    """Relationship between two graph objects."""

    model_config = ConfigDict(extra="forbid")

    id: str
    relation_type: str
    source_id: str
    target_id: str
    source_type: str
    target_type: str
    source_module_id: str
    target_module_id: str
    summary: str = ""


class Span(BaseModel):
    """Source span used for anchoring and navigation."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    line_start: int
    line_end: int
    module_id: str
    file_id: str
    symbol_id: str | None = None
    node_type: str


class GraphCode(BaseModel):
    """Top-level graph container."""

    model_config = ConfigDict(extra="forbid")

    repo_meta: RepoMeta
    modules: list[Module] = Field(default_factory=list)
    files: list[File] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
