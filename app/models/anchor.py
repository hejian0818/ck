"""Anchor model definitions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Anchor(BaseModel):
    """Resolved anchor for QA scope selection."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["module", "file", "symbol", "none"]
    source: Literal[
        "explicit_span",
        "explicit_file",
        "explicit_module",
        "name_match",
        "memory_inherit",
        "retrieval_infer",
        "none",
    ]
    confidence: float
    module_id: str | None = None
    file_id: str | None = None
    symbol_id: str | None = None
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
