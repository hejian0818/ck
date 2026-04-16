"""Metrics observation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_key
from app.core.metrics import metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def get_metrics() -> dict:
    """Return all collected metrics."""
    return metrics.snapshot()


@router.post("/reset", dependencies=[Depends(require_api_key)])
def reset_metrics() -> dict[str, str]:
    """Reset all metrics."""
    metrics.reset()
    return {"status": "ok"}
