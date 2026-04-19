"""Metrics observation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import require_api_key, require_rate_limit
from app.core.metrics import metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def get_metrics() -> dict:
    """Return all collected metrics."""
    return metrics.snapshot()


@router.get("/prometheus")
def get_prometheus_metrics() -> Response:
    """Return metrics in Prometheus text format."""

    return Response(content=metrics.prometheus_text(), media_type="text/plain; version=0.0.4")


@router.post("/reset", dependencies=[Depends(require_rate_limit), Depends(require_api_key)])
def reset_metrics() -> dict[str, str]:
    """Reset all metrics."""
    metrics.reset()
    return {"status": "ok"}
