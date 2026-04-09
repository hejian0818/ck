"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.doc import router as doc_router
from app.api.metrics import router as metrics_router
from app.api.qa import router as qa_router
from app.api.repo import router as repo_router
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="CodeWiki", version="0.1.0")
app.include_router(repo_router)
app.include_router(qa_router)
app.include_router(doc_router)
app.include_router(metrics_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Basic health endpoint."""

    return {"status": "ok"}
