"""LangGraph checkpoint helpers."""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_exit_stack = ExitStack()
_checkpointer: Any | None = None


def get_langgraph_checkpointer() -> Any | None:
    """Return a process-wide LangGraph checkpointer when configured."""

    global _checkpointer
    if not settings.LANGGRAPH_CHECKPOINT_ENABLED:
        return None
    if _checkpointer is not None:
        return _checkpointer

    checkpoint_url = settings.LANGGRAPH_CHECKPOINT_URL or settings.DATABASE_URL
    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        context_manager = PostgresSaver.from_conn_string(checkpoint_url)
        checkpointer = _exit_stack.enter_context(context_manager)
        checkpointer.setup()
        _checkpointer = checkpointer
    except Exception as exc:  # pragma: no cover - depends on optional deployment config
        logger.warning(
            "langgraph_checkpointer_unavailable",
            extra={"context": {"error": str(exc)}},
        )
        _checkpointer = None
    return _checkpointer
