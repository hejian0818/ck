"""API validation and error helpers."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

from fastapi import HTTPException

from app.core.config import settings


def handle_api_error(exc: Exception) -> NoReturn:
    """Convert internal exceptions to stable HTTP errors."""

    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, NotADirectoryError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def validate_repo_path(repo_path: str) -> str:
    """Resolve and validate a repository path before scanning."""

    resolved = Path(repo_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Repository path does not exist: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {resolved}")

    allowed_roots = _allowed_roots()
    if allowed_roots and not any(_is_relative_to(resolved, root) for root in allowed_roots):
        allowed = ", ".join(str(root) for root in allowed_roots)
        raise PermissionError(f"Repository path must be under one of: {allowed}")

    return str(resolved)


def _allowed_roots() -> list[Path]:
    return [
        Path(raw_root).expanduser().resolve()
        for raw_root in settings.REPO_SCAN_ALLOWED_ROOTS.split(":")
        if raw_root.strip()
    ]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
